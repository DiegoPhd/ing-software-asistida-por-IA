# Plan de Implementación: Runtime PostgreSQL en contenedores (H004)

**Rama de trabajo**: `diego.betancourt/taller-autonomo` (rama actual) · **Rama de la funcionalidad**:
`004-postgres-container-runtime`

**Fecha**: 2026-11-23 | **Spec**: [spec.md](./spec.md)

**Entrada**: Especificación `specs/004-postgres-container-runtime/spec.md`: preparar IncidentOps
para ejecutarse en contenedores con una base PostgreSQL dedicada y un chequeo real de conectividad,
sin romper la ruta local sin infraestructura ni la paridad REST/CLI. Respaldada por ADR-007, ADR-008
y la Constitución §III–§VI.

> Nota de rama: `setup-plan.ps1` informó `BRANCH=004-postgres-container-runtime`, pero la rama
> actual del repositorio es `diego.betancourt/taller-autonomo`. El trabajo se desarrolla en la rama
> actual y se integra por PR a `main`; si se crea la rama de funcionalidad, debe partir de `main` y
> no de un estado parcial. El árbol de trabajo ya contiene `psycopg[binary]` en `pyproject.toml` y
> `uv.lock`; el plan verifica esa dependencia, no la vuelve a introducir.

## Resumen

H004 añade tres piezas y no toca el núcleo: un **adaptador PostgreSQL** que implementa el mismo
`IncidentRepositoryPort` con `psycopg` y `dict_row`, una **fábrica** que selecciona SQLite o
PostgreSQL a partir de `DATABASE_URL`, y una **capacidad de salud** (`IncidentService.check_health`)
expuesta con paridad en `GET /health` (200/503) y `cli health` (salida 0/1). Alrededor de eso se
empaqueta el runtime con `Dockerfile`, `.dockerignore` y un `docker-compose.yml` de dos servicios
(`db` y `api`) con volumen nombrado, healthchecks y arranque ordenado.

La salud es una comprobación de conectividad real por petición (`SELECT 1`), sin caché y sin DDL: el
esquema se asegura de forma idempotente al componer el repositorio cuando la base responde y se
reintenta en la primera operación de negocio si no estaba disponible. El adaptador PostgreSQL no
calcula SLA, similitud, claves de grupo ni ordena; replica la semántica de escritura estricta y de
errores de SQLite. El alta usa `INSERT` estricto; `ON CONFLICT DO UPDATE` se reserva a la siembra
idempotente de `sla_policies`, nunca a `incidents`.

## Contexto Técnico

**Lenguaje / Versión**: Python >= 3.10 en desarrollo (compatible con H001–H003); imagen de runtime
`python:3.12-slim`, gestionada con `uv`, `[tool.uv] package = false` e imports absolutos desde la raíz.

**Dependencias principales**: FastAPI + Pydantic v2 (REST), Typer (CLI), Uvicorn (servidor),
`sqlite3` de la biblioteca estándar y `psycopg[binary]` (ADR-007). Sin ORM, sin Alembic, sin
`psycopg2`, sin pooler y sin PyYAML. `psycopg[binary]` ya figura en `pyproject.toml` y `uv.lock` del
árbol de trabajo; `httpx`, `pytest` y `ruff` siguen en el grupo `dev`.

**Almacenamiento**:
- SQLite: valor por defecto y ruta local (`:memory:` o archivo), sin cambios de esquema.
- PostgreSQL 16: tablas `incidents` y `sla_policies` con columnas `TEXT`/`INTEGER`, los índices
  `idx_incidents_component_status` y `idx_incidents_dup_key`, DDL idempotente y siembra de políticas.
- `created_at` y `resolved_at` se persisten como texto ISO 8601 naive con microsegundos en ambos
  motores; nunca `TIMESTAMP`/`TIMESTAMPTZ`, época numérica ni `now()`.
- Conexiones PostgreSQL de corta duración por operación con `connect_timeout=2` y `row_factory=dict_row`;
  inicialización de esquema perezosa y reintentable.

**Pruebas**: `pytest` con `TestClient`, `CliRunner` y dobles en memoria. La suite base corre sin
Docker, sin red y sin base real (RNF-001). La suite de contrato parametriza SQLite y PostgreSQL y se
omite en el segundo si no hay `TEST_POSTGRES_URL`. Las pruebas de Docker son estructurales (lectura de
texto y expresiones regulares); la verificación real vive en `tools/verify_runtime.py`.

**Plataforma objetivo**: Windows, macOS y Linux con Python ≥ 3.10; despliegue de referencia con
Docker Compose en un solo host; API servida por Uvicorn sobre FastAPI.

**Tipo de proyecto**: aplicación única Python con dos adaptadores de entrada (REST y CLI) y dos
adaptadores de salida intercambiables (SQLite y PostgreSQL).

**Objetivos de rendimiento**: `/health` con la base sana p95 ≤ 200 ms en local; con la base caída,
503 en ≤ 3 s y comprobación ≤ 2 s (RNF-002); tras volver la base, 200 en ≤ 5 s sin reiniciar la API
(RNF-005); el benchmark de 10 000 incidentes conserva los objetivos de H003 (RNF-006).

**Restricciones**:
- `psycopg` solo se importa desde `src/adapters/outbound/`; `DATABASE_URL` solo se lee en la fábrica
  (RNF-009).
- La frontera `adapters → application → domain` no cambia; el dominio no conoce motores ni salud.
- Credenciales solo por entorno; nunca en la imagen, logs, documentos de salud ni mensajes de error.
- Sin migración de datos SQLite, sin migraciones versionadas y sin publicar la base al host.
- Ruff obligatorio (`E4`, `E7`, `E9`, `F`, `TID`) con las reglas de frontera activas.

**Escala / Alcance**: una réplica de API, una base, 10 000 incidentes activos, 6 componentes, 4
severidades, 2 estados activos; una capacidad nueva (salud) × 2 canales; dos motores de persistencia.

## Verificación de la Constitución

*PUERTA: debe pasar antes de la Fase 0. Reevaluada tras el diseño de la Fase 1.*

No se requiere enmienda. La Constitución vigente es la **1.2.0** (la spec cita 1.1.1; prevalece el
archivo `.specify/memory/constitution.md`). ADR-007 ya autoriza el adaptador PostgreSQL y ADR-008 la
topología Compose; el Principio IV ya declara `check_health` en el puerto, por lo que H004 solo añade
el caso de uso y los adaptadores.

| Principio / invariante | Estado | Evidencia o acción requerida |
|---|---|---|
| I. Núcleo determinista único | PASS | `src/domain/` no se modifica. `Incident`, `SLARule`, `SLAEvaluation` y las reglas de duplicados siguen siendo la única definición; los DTO de salud solo contienen `status` y `database`. |
| II. Dominio puro y auditable | PASS | Sin imports nuevos ni reloj/E/S en el dominio. La salud no entra en `src/domain/`; es conectividad de infraestructura. |
| III. Arquitectura hexagonal estricta | PASS | `PostgresIncidentRepository` vive en `outbound/`; la aplicación solo delega `check_health`; el inbound solo traduce a HTTP/CLI. Ningún adaptador importa otro adaptador concreto. |
| IV. Puertos explícitos y composición única | PASS | `IncidentRepositoryPort.check_health() -> bool` ya existe y no cambia de firma. `factory.create_repository` es el único punto que interpreta `DATABASE_URL`, instancia SQLite o PostgreSQL e inyecta `SystemClock`. |
| V. Stack gobernado | PASS | `psycopg[binary]` está aprobado por ADR-007 y la Constitución §V; Docker Compose por ADR-008. No se añaden ORM, migrador, pooler ni lector YAML. |
| VI. Fronteras verificadas con Ruff | PASS | Se añaden `psycopg`, `psycopg2` y `src.adapters.outbound.postgres_repository` a las prohibiciones de `inbound/` y de `inbound/api/`. Dominio y aplicación ya los prohíben. `uv run ruff check src/` debe pasar sin `noqa` nuevos. |
| VII. BDD y pruebas ejecutables | PASS | `tests/test_spec_004_runtime_health.py` cubre E-01…E-06 con dobles; `tests/adapters/test_factory.py` y `tests/contract/test_repository_contract.py` cubren la matriz de DSN y la paridad. Sin `sleep` en pruebas de dominio. |
| Contrato de persistencia entre motores | PASS con precisión | La ruta de alta usa `INSERT` estricto y traduce `UniqueViolation` a `IncidentAlreadyExistsError`. `ON CONFLICT DO UPDATE` se usa **solo** en la siembra idempotente de `sla_policies`, que no es la ruta de alta (equivale al `INSERT OR REPLACE` de siembra de SQLite) y queda fuera de la prohibición de ADR-007 §3e. Ver [research.md](./research.md) D5. |
| Invariantes de SLA | PASS | No se tocan la política, el 75 %, la ventana hábil ni el incumplimiento estricto. El adaptador no calcula SLA. |
| Estados del incidente | PASS | Sin cambios; el adaptador PostgreSQL valida los mismos estados y `resolved_at` en terminales. |
| Deuda deliberada | PASS | Los festivos siguen sin descontarse (ADR-002); `legacy/triage_rules.py` sigue congelado; no se reintroduce deuda de H002; `CONTEXT_LOG.md` no se reescribe. |
| Gobernanza documental | PASS | No hace falta ADR nuevo: ADR-007 y ADR-008 ya registran las decisiones. Se actualizan `AGENTS.md`, `README.md` y `docs/ROADMAP.md` (H004 → entregado) en el mismo PR. |

**Reevaluación tras el diseño de la Fase 1**: se mantiene. Los contratos nuevos (salud y DSN) no
introducen capas ni tipos de dominio paralelos; `inbound/health_contract.py` es un contrato de
transporte compartido, con el mismo precedente que `summary_contract.py` y `lifecycle_contract.py`, y
no crea una arista entre adaptadores concretos. La conexión por operación no añade estado de negocio.

## Estructura del Proyecto

### Documentación (esta funcionalidad)

```text
specs/004-postgres-container-runtime/
├── plan.md                          # Este documento
├── research.md                      # Fase 0 · D1–D14 con alternativas
├── data-model.md                    # Fase 1 · salud, DSN, esquema PostgreSQL, ciclo de vida
├── quickstart.md                    # Fase 1 · validación local, Compose y caos controlado
├── contracts/
│   ├── health-api.md                # GET /health · 200/503
│   ├── health-cli.md                # health · salida 0/1/2
│   ├── health.schema.json           # Documento canónico de salud
│   ├── database-url.md              # Matriz de selección y seguridad del DSN
│   └── runtime-compose.md           # Servicios, orden, variables, volumen e imagen
└── tasks.md                         # Fase 2 (/speckit.tasks), no se crea aquí
```

### Código fuente (raíz del repositorio)

```text
src/
├── domain/                          # SIN CAMBIOS
├── application/
│   ├── ports.py                     # SIN CAMBIOS · check_health ya declarado
│   └── services.py                  # MODIFICADO · IncidentService.check_health()
└── adapters/
    ├── inbound/
    │   ├── health_contract.py       # NUEVO · HealthResponse, to_health_response
    │   ├── api/app.py               # MODIFICADO · GET /health 200/503, no-store, versión 0.4.0
    │   ├── api/schemas.py           # SIN CAMBIOS · el contrato de salud es compartido
    │   ├── cli.py                   # MODIFICADO · comando health y CONFIG_DATABASE_URL_INVALIDA
    │   ├── problem.py               # MODIFICADO · títulos de los códigos nuevos
    │   ├── ruff.toml                # MODIFICADO · prohíbe psycopg y el adaptador PostgreSQL
    │   └── api/ruff.toml            # MODIFICADO · mismas prohibiciones en el paquete HTTP
    └── outbound/
        ├── postgres_repository.py   # NUEVO · PostgresIncidentRepository
        ├── factory.py               # MODIFICADO · matriz SQLite/PostgreSQL y vacío inválido
        └── sqlite_repository.py     # MODIFICADO · microsegundos en created_at/resolved_at

Dockerfile                           # NUEVO · multietapa, uv.lock, usuario no root
.dockerignore                        # NUEVO · secretos, VCS, entornos, cachés y datos
docker-compose.yml                   # NUEVO · db + api, volumen, healthchecks, depends_on
.env.example                         # NUEVO · marcadores de credenciales locales

tests/
├── test_spec_004_runtime_health.py  # NUEVO · E-01…E-06, salud HTTP/CLI y estructura Docker
├── adapters/
│   ├── test_factory.py              # NUEVO · matriz de DSN y puerto en ambos motores
│   ├── test_api.py                  # MODIFICADO · cuerpo nuevo de /health
│   └── test_sqlite_repository.py    # MODIFICADO · vacío inválido y microsegundos
├── application/
│   └── test_services.py             # MODIFICADO · delegación de check_health
└── contract/
    └── test_repository_contract.py  # NUEVO · misma suite SQLite/PostgreSQL (omite sin motor)

tools/
└── verify_runtime.py                # NUEVO · --compose y --compose --resiliencia (O-01/O-02)

docs/ROADMAP.md, AGENTS.md, README.md  # MODIFICADOS · H004, comandos, salud y Compose
```

**Decisión de estructura**: se mantiene un único proyecto Python. El dominio no se toca. La
aplicación gana un caso de uso de delegación. El inbound comparte `health_contract.py` entre HTTP y
CLI porque la frontera prohíbe que el CLI importe `api/`; `HealthResponse` se usa como
`response_model` en `api/app.py`, que es el punto donde la spec la ubica funcionalmente. El outbound
concentra DDL, SQL, siembra y mapeo de ambos motores, sin que uno importe al otro (ADR-007 §4). La
raíz aloja el empaquetado y el despliegue de referencia.

## Fase 0 · Investigación

Salida: [research.md](./research.md). No quedan `NEEDS CLARIFICATION`. Resumen de decisiones:

| # | Decisión | Motivo central |
|---|---|---|
| D1 | `HealthResponse` y `to_health_response` en `inbound/health_contract.py` | Paridad HTTP/CLI sin que el CLI importe `api/` (FR-003, SC-003) |
| D2 | `IncidentService.check_health()` delega en el puerto sin capturar | FR-004; la no-excepción es obligación del adaptador (FR-005) |
| D3 | Conexión PostgreSQL por operación, esquema perezoso y `connect_timeout=2` | Arranque tolerante, recuperación sin reinicio y 503 acotado (FR-010/FR-011, RNF-002) |
| D4 | Fábrica distingue ausencia de vacío; `postgres://` rechazado | FR-006/SC-007 y ADR-007; sin fallback silencioso |
| D5 | `ON CONFLICT DO UPDATE` solo en siembra de políticas; `INSERT` estricto en alta | Idempotencia equivalente a SQLite sin violar la prohibición de UPSERT en alta |
| D6 | Mapeo y validación duplicados dentro del adaptador PostgreSQL | ADR-007 §4 acepta dos DDL/mapeos; prohibido importar otro adaptador |
| D7 | Microsegundos en ambos motores | FR-009 y contrato de persistencia de la Constitución |
| D8 | `JSONResponse` 200/503 con `Cache-Control: no-store` | Cuerpos exactos, nunca 500 y sin caché (FR-001/FR-002) |
| D9 | `health` sale 0/1; configuración inválida sale 2 con `CONFIG_DATABASE_URL_INVALIDA` | FR-003/FR-018 y separación stdout/stderr |
| D10 | Imagen multietapa con `uv sync --frozen --no-dev`, no root y healthcheck con `urllib` | FR-013, RNF-007; sin `curl` en slim |
| D11 | Compose con `db` sana antes de `api`, volumen nombrado y marcadores locales por entorno | FR-014/FR-015, SC-004, RNF-011 |
| D12 | `.dockerignore` excluye secretos, VCS, entornos, cachés, pruebas y datos | FR-016 y RNF-007 |
| D13 | Suite sin Docker; contrato PostgreSQL opcional por `TEST_POSTGRES_URL`; Docker estructural | RNF-001/RNF-013 y C-02 |
| D14 | Ruff prohíbe `psycopg` y el adaptador concreto en `inbound/` | RNF-009 y Principio VI |

## Fase 1 · Diseño y Contratos

Salidas: [data-model.md](./data-model.md), [contracts/health-api.md](./contracts/health-api.md),
[contracts/health-cli.md](./contracts/health-cli.md),
[contracts/health.schema.json](./contracts/health.schema.json),
[contracts/database-url.md](./contracts/database-url.md),
[contracts/runtime-compose.md](./contracts/runtime-compose.md) y [quickstart.md](./quickstart.md).

Puntos contractuales fijados:

- **Salud HTTP**: `GET /health` → `200` con `{"status":"ok","database":"connected"}` o `503` con
  `{"status":"error","database":"unavailable"}`; `Content-Type: application/json` y
  `Cache-Control: no-store` en ambos; sin autenticación, sin caché y sin detalles internos.
- **Salud CLI**: `health` escribe el mismo documento en stdout y sale `0`/`1`. Configuración inválida:
  `problem+json` en stderr con `CONFIG_DATABASE_URL_INVALIDA`, salida `2`, sin documento ni traza.
- **Configuración**: variable ausente o `sqlite:///:memory:` → memoria; `sqlite:///ruta` → archivo;
  `postgresql://…` → PostgreSQL; vacío, solo espacios, `postgres://` o cualquier otro esquema →
  `ConfigurationError` antes de abrir conexión. Único intérprete: `factory.py`.
- **Puerto**: `IncidentRepositoryPort` conserva sus cinco métodos. `check_health` devuelve `True` solo
  si `SELECT 1` obtiene fila, `False` ante cualquier fallo y nunca lanza ni ejecuta DDL.
- **Alta**: `INSERT` estricto; `UniqueViolation` → `IncidentAlreadyExistsError`; la fila previa no se
  modifica. `ON CONFLICT DO UPDATE` solo siembra `sla_policies`.
- **Lecturas**: columnas explícitas, `INNER JOIN sla_policies` donde H003 lo usa, filtro de activos,
  dos variantes para el filtro por componente y ningún cálculo de SLA, similitud, clave ni orden.
- **Tiempo**: texto ISO 8601 naive con microsegundos en ambos motores; lectura con `fromisoformat`.
- **Runtime**: `db` (`postgres:16-alpine`, volumen `incidentops_pgdata`, `pg_isready`) y `api`
  (build local, `DATABASE_URL` hacia `db`, `depends_on: service_healthy`, healthcheck sobre `/health`,
  puerto `${API_PORT:-8000}`, una réplica). La base no se publica al host.
- **Imagen**: `python:3.12-slim` multietapa, `uv sync --frozen --no-dev`, usuario UID/GID 10001,
  Uvicorn en `0.0.0.0:8000`, sin credenciales ni estado persistente.

### Trazabilidad de pruebas

| Escenario | Archivo / prueba |
|---|---|
| E-01 / E-03 (`/health` 200 y 503) | `tests/test_spec_004_runtime_health.py::test_bdd_e01_*`, `::test_bdd_e03_*` |
| E-02 / E-04 (consola conectada y caída) | `::test_bdd_e02_*`, `::test_bdd_e04_*` |
| E-05 (paridad de canales) | `::test_bdd_e05_*`, parametrizada conectado/no disponible |
| E-06 (desarrollo local sin base dedicada) | `::test_bdd_e06_*` |
| C-01 (selección por DSN y puerto) | `tests/adapters/test_factory.py` |
| C-02 (contrato SQLite/PostgreSQL) | `tests/contract/test_repository_contract.py` |
| O-01 / O-02 (Compose y resiliencia) | `tools/verify_runtime.py --compose [--resiliencia]` |

> La spec referencia `tests/test_bdd_h004_salud_runtime.py`, pero el nombre solicitado para este
> hito es `tests/test_spec_004_runtime_health.py`, coherente con `test_spec_001…003`. El archivo nuevo
> conserva los nombres `test_bdd_e01…e06`; la traza de la spec se actualiza en el mismo PR.

## Orden de Implementación

1. **Aplicación**: añadir `IncidentService.check_health()` que delega en
   `IncidentRepositoryPort.check_health()`; cubrirlo con un doble en `tests/application/test_services.py`.
2. **Salida · fábrica**: separar ausencia de vacío en `factory.py`, rechazar `postgres://`, añadir la
   rama `postgresql://` y conservar `resolve_database_path` como helper de SQLite. Trasladar la matriz
   de DSN a `tests/adapters/test_factory.py` y actualizar las expectativas antiguas (`""` ya no es
   memoria y `postgresql://` ya no es error).
3. **Salida · PostgreSQL**: crear `postgres_repository.py` con `dict_row`, DDL idempotente, índices,
   siembra con `ON CONFLICT DO UPDATE`, `INSERT` estricto con traducción de unicidad, lecturas con
   columnas explícitas y `check_health` acotado. Replicar la validación y el mapeo sin importar SQLite.
4. **Salida · SQLite**: normalizar `created_at`/`resolved_at` a microsegundos para cumplir FR-009 sin
   cambiar los `datetime` leídos.
5. **Entrada · contrato de salud**: crear `health_contract.py`; registrar `GET /health` con 200/503,
   `no-store` y versión `0.4.0`; añadir `health` a la CLI con sus códigos de salida; añadir los títulos
   `CONFIG_DATABASE_URL_INVALIDA` y `HEALTH_ERROR_INTERNO` a `problem.py`.
6. **Fronteras**: ampliar `inbound/ruff.toml` y `api/ruff.toml` con `psycopg`, `psycopg2` y
   `src.adapters.outbound.postgres_repository`.
7. **Runtime**: crear `Dockerfile`, `.dockerignore`, `docker-compose.yml` y `.env.example`; verificar
   `uv.lock` con `uv sync --frozen`.
8. **Pruebas**: escribir `test_spec_004_runtime_health.py` (E-01…E-06, CLI y estructura Docker),
   `test_factory.py`, `test_repository_contract.py` y actualizar `test_api.py`.
9. **Herramientas y documentación**: crear `tools/verify_runtime.py`; actualizar `README.md`,
   `AGENTS.md` y `docs/ROADMAP.md`; registrar la traza final de la spec.
10. **Validación**: `uv run ruff check src/`, `uv run pytest -q` y, si Docker está disponible,
    `uv run python tools/verify_runtime.py --compose --resiliencia`.

## Seguimiento de Complejidad

| Desviación | Por qué se necesita | Alternativa más simple rechazada |
|---|---|---|
| Dos DDL, dos mapeos y dos juegos de consultas | ADR-007 §4 los acepta explícitamente para no acoplar adaptadores; la paridad se prueba con contrato | Adaptador único multipropósito o importar SQLite desde PostgreSQL: acopla adaptadores y oculta el dialecto |
| Conexión PostgreSQL por operación en lugar de conexión persistente | Arranque tolerante, recuperación sin reinicio y salud honesta sin lógica de reconexión | Pooler o conexión compartida: dependencia y estado compartido fuera de alcance |
| `ON CONFLICT DO UPDATE` en `sla_policies` | Idempotencia equivalente al `INSERT OR REPLACE` de siembra de SQLite | `DO NOTHING`: no actualizaría políticas cambiadas; UPSERT en `incidents`: prohibido |
| Normalizar microsegundos también en SQLite | FR-009 y el contrato de persistencia exigen el mismo formato en ambos motores | Dejar SQLite sin microsegundos: divergencia real entre motores |
| `health_contract.py` fuera de `api/` | El CLI no puede importar `api/` (Ruff `TID251`) y SC-003 exige paridad exacta | Duplicar el modelo en la CLI o importar `api/schemas.py`: frontera rota o deriva de contrato |
| Pruebas de Docker por lectura de texto | Evitan PyYAML y el daemon en la suite; detectan regresiones de configuración | `testcontainers` o `PyYAML`: dependencias nuevas y suite dependiente de Docker |

## Riesgos y Mitigaciones

| Riesgo | Mitigación |
|---|---|
| La suite se vuelve dependiente de Docker o de un PostgreSQL real | Dobles en memoria para salud y aceptación; contrato PostgreSQL omitido sin `TEST_POSTGRES_URL`; Docker solo en `tools/verify_runtime.py` |
| El `ON CONFLICT DO UPDATE` se interpreta como UPSERT de alta | Solo existe en la siembra de `sla_policies`; una prueba de conflicto verifica que un alta duplicada no modifica la fila previa |
| El esquema PostgreSQL no existe cuando llega una operación | `_ensure_schema()` idempotente al componer y reintento bajo cerrojo en cada operación; la salud no hace DDL |
| La base cae y la API queda con una conexión rota | Conexiones por operación, `connect_timeout=2` y `check_health` que devuelve `False`; recuperación sin reinicio |
| Divergencia de valores entre motores | Misma suite de contrato, columnas explícitas, microsegundos en ambos y pruebas de error/orden |
| Credenciales filtradas en mensajes o imágenes | `ConfigurationError` cita solo el esquema; `.env` ignorado y `.dockerignore`; sin `ARG` de secretos |
| El build de Compose tarda o falla por `README.md`/`uv.lock` | El builder copia `pyproject.toml`, `uv.lock` y `README.md` y usa `uv sync --frozen --no-dev` |
| El healthcheck del contenedor no tiene `curl` | Se usa `python -c` con `urllib.request`; un 503 lanza `HTTPError` y marca el contenedor no sano |
| `DATABASE_URL` vacía en un despliegue incompleto cae a memoria | La fábrica distingue ausencia de vacío y lanza `ConfigurationError` antes de abrir conexión |
| La contraseña contiene `@`, `:` o `/` y rompe el DSN | Se documenta la codificación URL en `contracts/database-url.md` y en `.env.example` |
| `:memory:` no comparte datos entre conexiones | La ruta local documentada usa archivo cuando se necesita persistencia; las pruebas de salud usan dobles |

## Criterios de Cierre

- `uv run ruff check src/` sin errores, con `TID251`/`TID252` activos y sin `noqa` nuevos.
- `uv run pytest -q` en verde sin Docker, sin red y sin base real; H001–H003 sin cambios de
  comportamiento.
- `tests/test_spec_004_runtime_health.py` cubre `/health` 200, `/health` 503 con doble, paridad
  HTTP/CLI, `health` de la CLI y la estructura de `Dockerfile`, `.dockerignore`, `docker-compose.yml`
  y `.env.example`.
- `create_repository` demuestra por prueba que tanto SQLite como PostgreSQL cumplen
  `IncidentRepositoryPort`, que `postgresql://` selecciona PostgreSQL (con un DSN local no alcanzable
  que prueba que construir el repositorio no exige un motor vivo) y que vacío, `postgres://` y
  esquemas no admitidos fallan sin abrir conexión.
- La suite de contrato pasa en SQLite y, con motor disponible, en PostgreSQL con cero divergencias.
- `tools/verify_runtime.py --compose --resiliencia` deja evidencia de arranque ordenado, 200→503→200,
  persistencia tras recrear la API y reiniciar la base, y ausencia de credenciales en documentos.
- `README.md`, `AGENTS.md` y `docs/ROADMAP.md` actualizados; ADR-007/ADR-008 no requieren enmienda.
