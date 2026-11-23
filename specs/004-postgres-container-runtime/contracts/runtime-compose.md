# Contrato de runtime · Docker Compose

Topología de referencia de ADR-008: una red privada de Compose, un volumen nombrado y dos servicios
con ciclos de vida independientes.

## Servicios

| Servicio | Imagen / build | Responsabilidad | Réplicas |
|---|---|---|---|
| `db` | `postgres:16-alpine` | Base dedicada con volumen `incidentops_pgdata` sobre `PGDATA` | 1 |
| `api` | build local desde `Dockerfile` | Uvicorn + FastAPI; REST y CLI | 1 |

## Orden de arranque

```text
db inicia
  └─ healthcheck pg_isready ── sano ──> api inicia
                                          └─ healthcheck GET /health ── 200 ──> healthy
```

- `api` declara `depends_on: db: condition: service_healthy`; no arranca antes de que la base esté
  sana.
- El healthcheck de `api` consulta `/health` con `python -c` y `urllib.request` (la imagen slim no
  incluye `curl`). Un 503 mantiene el contenedor como no sano.
- Si la base cae después del arranque, `api` sigue ejecutándose y responde 503; cuando la base vuelve,
  `/health` responde 200 sin reiniciar la API.

## Variables de entorno

| Variable | Servicio | Valor por defecto local | Obligatoria en producción |
|---|---|---|---|
| `POSTGRES_USER` | `db` | `incidentops` | Sí |
| `POSTGRES_PASSWORD` | `db` | `incidentops_local` (marcador de desarrollo) | Sí |
| `POSTGRES_DB` | `db` | `incidentops` | Sí |
| `DATABASE_URL` | `api` | construida hacia `db:5432` | Sí |
| `API_PORT` | `api` | `8000` | No |

- Los valores por defecto existen para cumplir "una sola orden desde un clon limpio" (SC-004/RNF-011)
  y son marcadores locales, no secretos reales.
- `.env.example` documenta los marcadores; `.env` está en `.gitignore`.
- La imagen no contiene `DATABASE_URL`, contraseñas ni estado persistente.
- La base no publica puertos al host. La API publica `API_PORT:8000`.

## Persistencia y ciclo de vida

| Acción | Efecto en datos |
|---|---|
| `docker compose restart api` | Se conservan |
| `docker compose up --force-recreate api` | Se conservan |
| `docker compose restart db` | Se conservan |
| `docker compose down` | Se conservan en el volumen nombrado |
| `docker compose down -v` | Se pierden: eliminación explícita del volumen |

## Imagen

- Multietapa sobre `python:3.12-slim`; dependencias fijadas por `uv.lock` con
  `uv sync --frozen --no-dev`; sin cadena de compilación en runtime.
- Usuario de sistema sin privilegios (UID/GID 10001).
- `CMD` sirve `src.adapters.inbound.api.app:app` con Uvicorn en `0.0.0.0:8000`.
- `.dockerignore` excluye `.env`, `.git`, `.venv`, cachés, bases locales, pruebas, especificaciones y
  documentación.

## Verificación

```bash
docker compose up -d --build --wait
curl -fsS http://127.0.0.1:8000/health
docker compose ps
docker compose down          # conserva datos
docker compose down -v       # elimina datos de forma explícita
```

`tools/verify_runtime.py --compose` automatiza el arranque ordenado y la salud;
`--resiliencia` añade la caída y recuperación de `db` y la recreación de `api`.
