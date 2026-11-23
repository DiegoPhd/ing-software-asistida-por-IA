---

description: "Lista de tareas para H004 · Runtime PostgreSQL en contenedores"
---

# Tareas: Runtime PostgreSQL en contenedores (H004)

**Entrada**: documentos de diseño de `specs/004-postgres-container-runtime/`

**Requisitos previos**: [plan.md](./plan.md) · [spec.md](./spec.md) · [research.md](./research.md) ·
[data-model.md](./data-model.md) · [contracts/](./contracts/) · [quickstart.md](./quickstart.md)

**Pruebas**: se incluyen porque la especificación exige escenarios BDD ejecutables y traza E-01…E-06,
C-01/C-02 y O-01/O-02; además, la Constitución §VII no acepta una capacidad sin pruebas en verde.

**Organización**: las tareas se agrupan por historia de usuario para que cada una sea implementable y
verificable por separado. Ambas historias son P1; se ejecuta US1 y después US2.

## Formato: `[ID] [P?] [Story] Descripción`

- **[P]**: puede ejecutarse en paralelo (archivo distinto, sin dependencia de una tarea incompleta).
- **[Story]**: `US1` o `US2`; las fases de Preparación, Fundamentos y Pulido no llevan etiqueta.
- Cada descripción incluye la ruta exacta del archivo que se crea o modifica.

## Convenciones de ruta

- Proyecto único: `src/`, `tests/`, `tools/` y los archivos de runtime en la raíz del repositorio.
- Los datos canónicos de campos y restricciones están en `data-model.md`; las tareas citan el campo
  exacto en lugar de repetir la restricción.

---

## Fase 1: Preparación (infraestructura compartida)

**Propósito**: confirmar la dependencia aprobada y cerrar las fronteras estáticas antes de escribir
código.

- [ ] T001 Verificar que `psycopg[binary]` está en `pyproject.toml` y `uv.lock`, ejecutar `uv sync --frozen` y confirmar que no hace falta ninguna dependencia adicional (rutas: `pyproject.toml`, `uv.lock`).
- [ ] T002 [P] Añadir `psycopg`, `psycopg2` y `src.adapters.outbound.postgres_repository` a las importaciones prohibidas de `src/adapters/inbound/ruff.toml`, junto a la prohibición ya existente de SQLite.
- [ ] T003 [P] Replicar las mismas tres prohibiciones en `src/adapters/inbound/api/ruff.toml` para que el paquete HTTP no pueda importar el driver ni el adaptador concreto de PostgreSQL.

---

## Fase 2: Fundamentos (requisitos previos bloqueantes)

**Propósito**: contrato de salud compartido y caso de uso de delegación que necesitan ambos canales y
ambas historias.

**⚠️ CRÍTICO**: ninguna historia puede cerrarse sin estas tareas.

- [ ] T004 [P] Crear `src/adapters/inbound/health_contract.py` con `HealthResponse` y `to_health_response(connected: bool)`; fijar la pareja canónica de `status`/`database` según `data-model.md` `HealthResponse.status` y `HealthResponse.database`, y serializar con `model_dump(mode="json")`.
- [ ] T005 [P] Añadir `IncidentService.check_health() -> bool` delegando en `IncidentRepositoryPort.check_health()` en `src/application/services.py` (sin SQL, sin frameworks y sin capturar excepciones) y cubrir la delegación con un doble del puerto en `tests/application/test_services.py`, citando `data-model.md` `IncidentRepositoryPort.check_health`.

**Punto de control**: el contrato de salud y el caso de uso existen; US1 puede exponerlos y US2 puede
reutilizarlos.

---

## Fase 3: Historia de Usuario 1 · Saber si el servicio puede atender contra su base real (Prioridad: P1) 🎯 MVP

**Objetivo**: exponer la conectividad real con paridad HTTP/CLI: `GET /health` 200/503 y `health` con
salida 0/1, más el error de configuración con salida 2.

**Prueba independiente**: con un doble conectado, HTTP responde 200 y la CLI sale 0 con el mismo
documento; con un doble no disponible, HTTP responde 503 y la CLI sale 1 con el mismo documento, sin
traza ni detalles internos. No requiere PostgreSQL ni Docker.

### Pruebas de la Historia de Usuario 1 (obligatorias por la especificación)

- [ ] T006 [P] [US1] Escribir las pruebas de aceptación E-01–E-04 en `tests/test_spec_004_runtime_health.py` usando `create_app(service)` con dobles en memoria y `CliRunner`: cuerpos exactos de `contracts/health-api.md` y `contracts/health-cli.md`, cabecera `Cache-Control: no-store`, salidas 0/1 y ausencia de traza o credenciales; comprobar que fallan antes de T008/T009.
- [ ] T007 [P] [US1] Actualizar `tests/adapters/test_api.py::test_health_responde_ok` para comprobar el cuerpo exacto nuevo `{"status": "ok", "database": "connected"}`, `content-type: application/json` y `Cache-Control: no-store`.

### Implementación de la Historia de Usuario 1

- [ ] T008 [P] [US1] Sustituir la ruta `/health` actual de `src/adapters/inbound/api/app.py` por `HealthResponse` como `response_model` y un `JSONResponse` que devuelva 200 o 503, `media_type="application/json"`, `Cache-Control: no-store`, la respuesta 503 documentada y la versión `0.4.0` de la aplicación; los cuerpos deben cumplir `data-model.md` `HealthResponse.status` y `HealthResponse.database`.
- [ ] T009 [P] [US1] Añadir el comando `health` a `src/adapters/inbound/cli.py`: construir el servicio con `build_incident_service()`, escribir solo el documento compartido en stdout, salir 0/1, traducir `ConfigurationError` a `CONFIG_DATABASE_URL_INVALIDA` en stderr con salida 2 y añadir la ruta defensiva `HEALTH_ERROR_INTERNO` con salida 1; importar desde `health_contract`, nunca desde `api/`.
- [ ] T010 [P] [US1] Añadir los títulos de `CONFIG_DATABASE_URL_INVALIDA` y `HEALTH_ERROR_INTERNO` a `src/adapters/inbound/problem.py` para que los documentos de error de la CLI tengan un título estable y legible.

**Punto de control**: US1 funciona sola con SQLite o dobles; `/health` y `health` coinciden y nunca
devuelven 500 por una caída.

---

## Fase 4: Historia de Usuario 2 · Operar el mismo servicio sin infraestructura y con infraestructura (Prioridad: P1)

**Objetivo**: seleccionar SQLite o PostgreSQL por `DATABASE_URL`, implementar el puerto completo en
PostgreSQL y empaquetar el despliegue de referencia con Compose, conservando paridad y persistencia.

**Prueba independiente**: la suite pasa sin Docker; con `TEST_POSTGRES_URL` la misma suite de contrato
pasa en PostgreSQL; `docker compose up --build` deja `db` sana antes que `api`, `/health` responde
200, los datos sobreviven a recrear la API y a reiniciar la base, y una caída de `db` se informa como
503 y se recupera sin reiniciar la API.

### Pruebas de la Historia de Usuario 2

- [ ] T011 [P] [US2] Añadir E-05/E-06 y el escenario de ruta local a `tests/test_spec_004_runtime_health.py`: HTTP y CLI producen los mismos valores de `status`/`database` en ambos estados, y la ausencia de `DATABASE_URL` informa `connected` sobre almacenamiento efímero sin contenedores ni credenciales.
- [ ] T012 [P] [US2] Crear `tests/adapters/test_factory.py` cubriendo toda la matriz de `data-model.md` §2, `isinstance(repository, IncidentRepositoryPort)` para SQLite y PostgreSQL, la selección de PostgreSQL con un DSN local no alcanzable (la construcción no debe exigir un servidor vivo) y `ConfigurationError` para vacío/solo espacios, `postgres://`, `sqlite://`, `sqlite:///` y otros esquemas.
- [ ] T013 [P] [US2] Crear `tests/contract/test_repository_contract.py` parametrizado sobre SQLite y PostgreSQL (omitir PostgreSQL si falta `TEST_POSTGRES_URL`): los cinco métodos del puerto, conflicto estricto sin sobrescritura, filtrado por activos y componente, candidatos a duplicado sin similitud, texto temporal que cumpla `data-model.md` `incidents.created_at` e `incidents.resolved_at`, y ausencia de ordenación o cálculo de SLA en el adaptador.
- [ ] T014 [US2] Añadir pruebas estructurales de Docker a `tests/test_spec_004_runtime_health.py` leyendo texto (sin PyYAML): `Dockerfile` usa `python:3.12-slim`, `uv sync --frozen`, un `USER` no root y Uvicorn; `.dockerignore` excluye `.env`, `.git`, `.venv`, cachés, pruebas y bases locales; `docker-compose.yml` define `db`/`api`, `postgres:16-alpine`, `pg_isready`, `condition: service_healthy`, un volumen nombrado y ningún puerto de base publicado al host; y `.env.example` existe con marcadores. Se ejecuta después de T011 porque ambas editan el mismo archivo de pruebas.
- [ ] T015 [P] [US2] Actualizar `tests/adapters/test_sqlite_repository.py`: `resolve_database_path("")` y `create_repository("")` ahora lanzan `ConfigurationError`, las rutas SQLite no cambian y las escrituras nuevas persisten `incidents.created_at`/`incidents.resolved_at` con el formato de microsegundos de `data-model.md`.

### Implementación de la Historia de Usuario 2

- [ ] T016 [US2] Crear `PostgresIncidentRepository` en `src/adapters/outbound/postgres_repository.py` con almacenamiento del DSN, `psycopg.connect(..., row_factory=dict_row, connect_timeout=2)` por operación, un `_ensure_schema()` perezoso protegido por cerrojo y `check_health()` que devuelve `False` ante cualquier `psycopg.Error`/`OSError` sin ejecutar DDL, según `data-model.md` `IncidentRepositoryPort.check_health`.
- [ ] T017 [US2] Añadir a `src/adapters/outbound/postgres_repository.py` el DDL idempotente, los índices y la siembra de políticas: `sla_policies` e `incidents` exactamente como `data-model.md` `sla_policies.severity`, `sla_policies.max_resolution_minutes`, `sla_policies.operates_24x7`, `incidents.incident_id`, `incidents.title`, `incidents.component`, `incidents.severity`, `incidents.status`, `incidents.created_at`, `incidents.resolved_at`, `incidents.raw_text`, `incidents.recommended_team` e `incidents.duplicate_group_key`; crear `idx_incidents_component_status` e `idx_incidents_dup_key`; sembrar las políticas con `INSERT ... ON CONFLICT (severity) DO UPDATE` únicamente.
- [ ] T018 [US2] Implementar `save_incident` de PostgreSQL en `src/adapters/outbound/postgres_repository.py` con la misma validación de invariantes que SQLite, un `INSERT` estricto sobre `data-model.md` `incidents.incident_id` y traducción de `UniqueViolation`/sqlstate 23505 a `IncidentAlreadyExistsError` sin modificar la fila previa.
- [ ] T019 [US2] Implementar `get_incident`, `find_open_duplicates` y `list_active_incidents` en `src/adapters/outbound/postgres_repository.py` con la proyección explícita de diez columnas, `INNER JOIN sla_policies` donde lo usa H003, filtro de estados activos, dos variantes SQL para el filtro opcional por componente, mapeo `dict_row → Incident` con `datetime.fromisoformat`, y sin ordenación, SLA, similitud ni lógica de clave de grupo.
- [ ] T020 [US2] Rehacer `create_repository()` y `resolve_database_path()` en `src/adapters/outbound/factory.py` conforme a `data-model.md` §2: distinguir ausencia de vacío/solo espacios, aceptar `sqlite:///:memory:`, `sqlite:///ruta` y `postgresql://`, rechazar `postgres://` y esquemas desconocidos con `ConfigurationError` antes de abrir conexión, y mantener el mensaje de error con solo el esquema (nunca el DSN).
- [ ] T021 [P] [US2] Normalizar `created_at` y `resolved_at` con `isoformat(timespec="microseconds")` en `src/adapters/outbound/sqlite_repository.py` para `data-model.md` `incidents.created_at` e `incidents.resolved_at`, sin cambiar los valores `datetime` que se leen.
- [ ] T022 [US2] Crear `Dockerfile` en la raíz del repositorio: multietapa sobre `python:3.12-slim`, imagen de `uv` fijada, `uv sync --frozen --no-dev --no-install-project` con `pyproject.toml`/`uv.lock`/`README.md`, runtime con `.venv` y `src/`, usuario de sistema UID/GID 10001, sin credenciales, `EXPOSE 8000` y `CMD ["uvicorn", "src.adapters.inbound.api.app:app", "--host", "0.0.0.0", "--port", "8000"]`.
- [ ] T023 [P] [US2] Crear `.dockerignore` en la raíz del repositorio excluyendo `.git`, `.env`, `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `.opencode`, `.specify`, `tests/`, `specs/`, `docs/`, `data/`, `legacy/`, `*.db`, `*.log` y `CONTEXT_LOG.md`, y conservando `pyproject.toml`, `uv.lock`, `README.md` y `src/`.
- [ ] T024 [P] [US2] Crear `.env.example` en la raíz del repositorio documentando `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL` y `API_PORT` con marcadores locales no secretos y una nota de que los caracteres especiales de la contraseña deben codificarse para URL.
- [ ] T025 [P] [US2] Crear `docker-compose.yml` en la raíz del repositorio con `db` (`postgres:16-alpine`, volumen nombrado `incidentops_pgdata` sobre `PGDATA`, healthcheck `pg_isready`, sin puertos de host) y `api` (build desde `Dockerfile`, `DATABASE_URL` hacia `db`, `depends_on: service_healthy`, healthcheck sobre `/health` con `python -c` y `urllib.request`, `ports: "${API_PORT:-8000}:8000"`, una réplica).
- [ ] T026 [P] [US2] Crear `tools/verify_runtime.py` con `--compose` y `--compose --resiliencia`: esperar a que ambos servicios estén sanos, comprobar 200, detener `db` y comprobar 503, reiniciar `db` y comprobar 200 sin reiniciar `api`, recrear `api` y verificar la persistencia, y hacer `docker compose down` sin `-v`; salir con código distinto de cero y un mensaje claro ante cualquier fallo.

**Punto de control**: ambos motores cumplen el puerto, el despliegue de referencia arranca ordenado y
la salud se recupera sola; H001–H003 conservan su comportamiento.

---

## Fase 5: Pulido y asuntos transversales

**Propósito**: documentación, trazabilidad y evidencia final.

- [ ] T027 [P] Actualizar `README.md`, `AGENTS.md` y `docs/ROADMAP.md` con los comandos de H004 (`health`, Compose, `DATABASE_URL`), el código de error nuevo `CONFIG_DATABASE_URL_INVALIDA`, el adaptador PostgreSQL y H004 marcado como entregado.
- [ ] T028 [P] Actualizar la traza de pruebas de `specs/004-postgres-container-runtime/spec.md` de `tests/test_bdd_h004_salud_runtime.py` a `tests/test_spec_004_runtime_health.py`, conservando los nombres `test_bdd_e01…e06`.
- [ ] T029 Ejecutar `uv run ruff check src/` y `uv run pytest -q`; corregir cualquier fallo de frontera (`TID251`/`TID252`), formato o paridad sin añadir `noqa` ni debilitar pruebas (rutas: `src/`, `tests/`).
- [ ] T030 Validar [quickstart.md](./quickstart.md) con Docker disponible: `uv run python tools/verify_runtime.py --compose --resiliencia` y los escenarios de persistencia y configuración inválida; registrar la evidencia (arranque ordenado, 200→503→200, datos conservados y ausencia de credenciales) en el PR.

---

## Dependencias y orden de ejecución

### Dependencias entre fases

- **Preparación (T001–T003)**: sin dependencias; T002 y T003 son paralelas.
- **Fundamentos (T004–T005)**: dependen de la Preparación y **bloquean** ambas historias; T004 y T005
  son paralelas.
- **US1 (T006–T010)**: depende de Fundamentos. Es el MVP y no requiere PostgreSQL ni Docker.
- **US2 (T011–T026)**: depende de Fundamentos. Su núcleo (fábrica y adaptador) puede empezar en
  paralelo con US1 si hay capacidad, pero E-05/E-06 y la recuperación necesitan US1 terminada.
- **Pulido (T027–T030)**: depende de que las historias deseadas estén completas.

### Dependencias entre historias

- **US1 (P1)**: sin dependencia de US2; se verifica con dobles y SQLite.
- **US2 (P1)**: la paridad de canales y la recuperación (T011, T030) dependen de US1; el adaptador
  PostgreSQL, la fábrica y el empaquetado no dependen de US1.

### Orden dentro de US1

T006/T007 (pruebas) → T008 (HTTP) → T009/T010 (CLI y problemas) → verificación del punto de control.

### Orden dentro de US2

T016 (esqueleto y salud) → T017 (DDL e índices) → T018 (escritura) → T019 (lecturas) → T020 (fábrica)
→ T021 (microsegundos SQLite). Las pruebas T011–T015 se escriben antes y deben fallar. El runtime
T022–T026 puede hacerse en paralelo con el adaptador, pero se valida al final.

---

## Oportunidades de paralelismo

### Preparación y Fundamentos

```text
T002 · Ruff de inbound          ─┐
T003 · Ruff del paquete HTTP    ─┴─ en paralelo
T004 · Contrato de salud        ─┐
T005 · Caso de uso check_health ─┴─ en paralelo
```

### Historia de Usuario 1

```text
T006 · BDD E-01…E-04            ─┐
T007 · test_api.py actualizado  ─┴─ pruebas en paralelo
T008 · GET /health              ─┐
T009 · CLI health               ├─ implementación en archivos distintos
T010 · títulos problem.py       ─┘
```

### Historia de Usuario 2

```text
T011 · E-05/E-06                ─┐
T012 · test_factory.py          │
T013 · contrato SQLite/Postgres ├─ pruebas en paralelo
T015 · test_sqlite_repository   ─┘

T014 · estructura Docker        (después de T011: mismo archivo)

T016 → T017 → T018 → T019 → T020   (mismo archivo, secuencial)
T021 · microsegundos SQLite        (paralelo tras T015)
T022 · Dockerfile                  ─┐
T023 · .dockerignore               │
T024 · .env.example                ├─ archivos distintos
T025 · docker-compose.yml          │
T026 · verify_runtime.py           ─┘
```

---

## Estrategia de implementación

### MVP primero (solo US1)

1. Completar Preparación y Fundamentos.
2. Completar US1 (T006–T010).
3. **DETENERSE Y VALIDAR**: `uv run pytest -q tests/test_spec_004_runtime_health.py` y una consulta
   manual a `/health` y `health` con SQLite o dobles. Sin Docker ni PostgreSQL.
4. Es un incremento entregable: la salud real ya funciona en la ruta local.

### Entrega incremental

1. Preparación + Fundamentos → contrato y caso de uso listos.
2. US1 → salud REST/CLI (MVP).
3. US2 → PostgreSQL, fábrica, Compose y resiliencia; la paridad se demuestra con la suite de contrato.
4. Pulido → documentación y evidencia de quickstart. Cada paso deja la suite anterior en verde.

### Estrategia de equipo en paralelo

1. Equipo completo: Preparación + Fundamentos.
2. Después: una persona en US1 (inbound) y otra en US2 (adaptador y fábrica); el empaquetado Docker
   puede ir en paralelo con archivos propios.
3. La integración final requiere US1 para la paridad y la recuperación, y valida todo con T029/T030.

---

## Notas

- Tareas `[P]` = archivos distintos y sin dependencia de una tarea incompleta.
- `[US1]`/`[US2]` permiten trazar cada tarea a su historia y a los escenarios de la especificación.
- Las pruebas se escriben antes de la implementación correspondiente y deben fallar primero.
- No se modifica `src/domain/` ni se añaden dependencias fuera de `psycopg[binary]`.
- No se usa `ON CONFLICT DO UPDATE` sobre `incidents`; solo en la siembra de `sla_policies`.
- No se añaden credenciales, DSN ni estado persistente a la imagen.
- Confirmar `uv run ruff check src/` y `uv run pytest -q` antes de cada punto de control.
