# Guía de Validación · Runtime PostgreSQL en contenedores (H004)

**Fecha**: 2026-11-23 | **Contratos**: [Salud HTTP](./contracts/health-api.md) ·
[Salud CLI](./contracts/health-cli.md) · [Esquema](./contracts/health.schema.json) ·
[`DATABASE_URL`](./contracts/database-url.md) · [Compose](./contracts/runtime-compose.md)

Todos los comandos se ejecutan desde la raíz del repositorio. Cada bloque indica el resultado
esperado; el detalle de campos está en los contratos y en [data-model.md](./data-model.md).

## 1 · Preparación

```bash
uv sync
uv run ruff check src/
uv run pytest -q
```

**Esperado**: Ruff sin errores con `TID251` activo y la suite en verde **sin Docker, sin red y sin
base real**. Las pruebas PostgreSQL de integración se omiten si no hay motor.

## 2 · Ruta local sin infraestructura

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING = "utf-8"
uv run uvicorn src.adapters.inbound.api.app:app --port 8000
```

En otra terminal:

```bash
curl -i http://127.0.0.1:8000/health
uv run python -m src.adapters.inbound.cli health
```

**Esperado**:

- HTTP `200`, `Content-Type: application/json`, `Cache-Control: no-store` y cuerpo exacto
  `{"status":"ok","database":"connected"}`.
- CLI: el mismo documento en stdout y salida `0`.

No se requiere Docker, variable de entorno ni credencial.

## 3 · Archivo SQLite compartido por HTTP y CLI

```powershell
$env:DATABASE_URL = "sqlite:///runtime-demo.db"
Remove-Item runtime-demo.db -ErrorAction SilentlyContinue
```

```bash
uv run python -m src.adapters.inbound.cli create \
  --incident-id INC-4001 \
  --raw-text "La pasarela de pagos está caída y ningún comercio puede cobrar." \
  --created-at 2026-11-20T10:00:00
curl -fsS "http://127.0.0.1:8000/api/v1/incidents/summary?reference_time=2026-11-20T12:00:00"
```

**Esperado**: el alta sale `0`, el resumen incluye `INC-4001` y la salud sigue informando
`connected`. El comportamiento de triaje, resumen, alta y SLA no cambia respecto de H003.

## 4 · Despliegue de referencia con PostgreSQL

```bash
docker compose up -d --build --wait
docker compose ps
curl -i http://127.0.0.1:8000/health
curl -fsS -X POST http://127.0.0.1:8000/api/v1/incidents \
  -H "Content-Type: application/json" \
  -d '{"incident_id":"INC-4001","raw_text":"La pasarela de pagos está caída y ningún comercio puede cobrar.","created_at":"2026-11-20T10:00:00"}'
```

**Esperado**:

- `db` queda `healthy` antes de que `api` arranque (`depends_on: service_healthy`).
- `api` queda `healthy` y responde `200` con `{"status":"ok","database":"connected"}`.
- `docker compose ps` muestra una sola réplica de `api` y la base sin puerto publicado al host.
- El alta responde `201` y persiste `INC-4001` en PostgreSQL.
- Primera construcción ≤ 60 s y arranques posteriores ≤ 20 s en un host de desarrollo estándar.

Como la base no se publica al host, la CLI se ejecuta **dentro** del contenedor para que use el mismo
`DATABASE_URL`:

```bash
docker compose exec api python -m src.adapters.inbound.cli health
```

**Esperado**: mismo documento que HTTP y salida `0`.

### 4.1 · Persistencia

```bash
docker compose restart api
curl --retry 5 --retry-delay 1 --retry-all-errors -fsS \
  http://127.0.0.1:8000/api/v1/incidents/INC-4001/sla
docker compose up -d --force-recreate api
curl --retry 5 --retry-delay 1 --retry-all-errors -fsS \
  http://127.0.0.1:8000/api/v1/incidents/INC-4001/sla
docker compose restart db
docker compose down
docker compose up -d --wait
curl --retry 5 --retry-delay 1 --retry-all-errors -fsS \
  http://127.0.0.1:8000/api/v1/incidents/INC-4001/sla
```

**Esperado**: el incidente se conserva tras reiniciar o recrear la API, reiniciar la base y hacer
`down` sin `-v`. Solo `docker compose down -v` elimina los datos, y es una acción explícita.

### 4.2 · Indisponibilidad y recuperación

```bash
docker compose stop db
curl -i http://127.0.0.1:8000/health
docker compose exec api python -m src.adapters.inbound.cli health
docker compose start db
curl -i --retry 5 --retry-delay 2 --retry-all-errors http://127.0.0.1:8000/health
```

**Esperado**:

| Paso | HTTP | Cuerpo | CLI |
|---|---|---|---|
| `db` detenida | `503` | `{"status":"error","database":"unavailable"}` | mismo JSON en stdout, salida `1` |
| `db` de nuevo arriba | `200` | `{"status":"ok","database":"connected"}` | mismo JSON, salida `0` |

- La respuesta 503 llega en ≤ 3 s y nunca es 500.
- No aparece traza, credencial, host ni mensaje del driver.
- La API no se reinicia: se recupera sola en ≤ 5 s.
- Una operación de negocio con la base caída conserva el error inesperado genérico (500 HTTP, salida 1
  CLI), sin códigos nuevos.

### 4.3 · Configuración inválida

```powershell
$env:DATABASE_URL = "postgres://incidentops:clave@localhost:5432/incidentops"
uv run python -m src.adapters.inbound.cli health
```

**Esperado**: stdout vacío, stderr con `application/problem+json`, `code`
`CONFIG_DATABASE_URL_INVALIDA`, salida `2` y ninguna traza. La API no arranca con ese valor.

Repetir con `DATABASE_URL=""`: mismo resultado, sin caer a almacenamiento en memoria.

## 5 · Paridad de motores

```bash
# SQLite
export DATABASE_URL="sqlite:///paridad.db"
uv run pytest -q tests/contract/test_repository_contract.py

# PostgreSQL real alcanzable desde el host.
# El despliegue de referencia no publica 5432; este contenedor es una decisión
# explícita y efímera, fuera de la topología de Compose.
docker run --rm -d --name incidentops-paridad \
  -e POSTGRES_USER=incidentops -e POSTGRES_PASSWORD=incidentops_local \
  -e POSTGRES_DB=incidentops -p 5432:5432 postgres:16-alpine

export TEST_POSTGRES_URL="postgresql://incidentops:incidentops_local@127.0.0.1:5432/incidentops"
uv run pytest -q tests/contract/test_repository_contract.py
docker stop incidentops-paridad
```

**Esperado**: la misma suite pasa en ambos motores con cero divergencias de valores, errores y orden.
Sin `TEST_POSTGRES_URL`, los casos PostgreSQL se omiten y la suite base sigue en verde.

## 6 · Verificación estructural y automatizada

```bash
uv run pytest -q tests/test_spec_004_runtime_health.py
uv run python tools/verify_runtime.py --compose
uv run python tools/verify_runtime.py --compose --resiliencia
```

**Esperado**:

- La prueba de especificación cubre `/health` 200, `/health` 503 con doble, selección de repositorio,
  paridad HTTP/CLI y estructura de `Dockerfile`, `.dockerignore`, `docker-compose.yml` y
  `.env.example`, todo sin Docker.
- `--compose` deja el despliegue sano y sale `0`.
- `--resiliencia` demuestra caída, 503, recuperación a 200 y persistencia de datos, y sale `0`.

## 7 · Limpieza

```bash
docker compose down
docker compose down -v   # solo si se quiere eliminar el volumen de datos
Remove-Item runtime-demo.db, paridad.db -ErrorAction SilentlyContinue
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
```

`docker compose down` conserva los datos; eliminar el volumen es la única pérdida admitida.
