# Investigación · Runtime PostgreSQL en contenedores (H004)

**Fecha**: 2026-11-23 | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

No quedan incógnitas `NEEDS CLARIFICATION`. Las diez clarificaciones de la spec se toman como
cerradas y las decisiones siguientes resuelven solo los puntos técnicos que el plan necesita antes de
diseñar. La investigación se apoya en ADR-004 (persistencia dual sin ORM), ADR-008 (topología
Compose) y la Constitución §III–§VI, no en documentación externa nueva.

## D1 · Contrato de salud compartido y ubicación de `HealthResponse`

- **Decisión**: declarar `HealthResponse` y `to_health_response(connected: bool)` en
  `src/adapters/inbound/health_contract.py`. `api/app.py` la usa como `response_model` de
  `GET /health`; `cli.py` la serializa con `model_dump(mode="json")`. El modelo es
  `status: Literal["ok", "error"]` y `database: Literal["connected", "unavailable"]`, y la función
  fija la pareja válida (`True → ok/connected`, `False → error/unavailable`).
- **Razón**: FR-003 exige que la consola no dependa del adaptador HTTP y SC-003 exige coincidencia
  exacta de campos y valores. El precedente de H003 (`lifecycle_contract.py`) demuestra que un
  contrato de transporte compartido es la forma de garantizar paridad sin que el CLI importe `api/`;
  Ruff ya prohíbe esa importación desde `inbound/`.
- **Alternativas consideradas**: (a) declarar `HealthResponse` en `api/schemas.py` e importarla desde
  el CLI: prohibido por la frontera y por `TID251`; (b) duplicar el modelo en la CLI: dos contratos y
  deriva de nombres; (c) construir el diccionario a mano en cada canal: no hay validación ni esquema
  único. Se descartan. La spec pide `HealthResponse` en la capa de entrada API; se satisface usándola
  allí como modelo de respuesta, aunque su definición viva en el contrato compartido para no romper
  la frontera.

## D2 · `IncidentService.check_health()` como caso de uso de delegación

- **Decisión**: añadir a `src/application/services.py`:

  `check_health(self) -> bool` que devuelve `self._repository.check_health()` sin capturar
  excepciones. El puerto ya declara `check_health() -> bool` desde H002; no cambia su firma.
- **Razón**: FR-004 exige un caso de uso en aplicación que delegue en el puerto; FR-005 deposita en
  el adaptador la obligación de no lanzar y de devolver `False` ante cualquier fallo de conectividad,
  autenticación o tiempo de espera. Capturar en el servicio duplicaría esa garantía y ocultaría
  adaptadores que incumplen el puerto.
- **Alternativas consideradas**: (a) llamar al repositorio directamente desde los adaptadores de
  entrada: rompe el Principio III y obliga a inyectar la clase concreta; (b) envolver en
  `try/except Exception: return False`: convierte errores de programación en "base caída" y difumina
  la causa; (c) un nuevo `HealthPort`: un `Protocol` con un solo método que ya existe en el puerto de
  persistencia, abstracción especulativa. Se descartan.

## D3 · Adaptador PostgreSQL: conexión por operación, inicialización perezosa y espera acotada

- **Decisión**: `PostgresIncidentRepository` guarda el DSN y abre una conexión de corta duración por
  operación con `psycopg.connect(dsn, row_factory=dict_row, connect_timeout=2)`. El constructor
  intenta `_ensure_schema()` una vez; si la base no responde, **no lanza**, deja el esquema marcado
  como no asegurado, y cada operación de negocio vuelve a intentarlo bajo un `threading.Lock`. La
  comprobación de salud nunca ejecuta DDL (`SELECT 1` únicamente).
- **Razón**: FR-010/FR-011 exigen que el proceso arranque y reporte 503 con la base caída, que se
  recupere sin reiniciar y que ninguna operación de negocio corra contra un esquema sin inicializar.
  Una conexión persistente quedaría rota tras una caída y exigiría lógica de reconexión; una conexión
  por operación es más simple, honesta con la salud y no comparte estado entre hilos. El límite de
  2 s cumple RNF-002 (respuesta 503 ≤ 3 s, comprobación ≤ 2 s).
- **Alternativas consideradas**: (a) `psycopg_pool.ConnectionPool`: dependencia y complejidad que la
  spec excluye (pooler fuera de alcance); (b) conexión única con `ping`/reconexión manual: estado
  compartido y fallos en cascada entre hilos; (c) fallar en el constructor si la base no responde:
  contradice el arranque tolerante exigido. Se descartan.
- **Consecuencia**: la construcción del repositorio no requiere un servidor vivo, lo que permite
  probar `create_repository("postgresql://…")` y el cumplimiento del puerto sin Docker.
- **Refinamiento tras la validación con Compose (T030)**: `connect_timeout=2` no acota la resolución
  DNS; con el contenedor `db` detenido, el nombre tarda ~3,9 s en fallar y el 503 superaba el
  presupuesto de 3 s de RNF-002. `check_health` impone ahora un **plazo total de 2 s** con un hilo de
  trabajo (`TIEMPO_DE_COMPROBACION_SEGUNDOS`): si el resultado no llega, informa `False` sin lanzar.
  Medición final: 503 en 2,01 s y recuperación en 0,5 s sin reiniciar la API.

## D4 · Selección por `DATABASE_URL`: ausencia, vacío y alias

- **Decisión**: `factory.py` lee el DSN una sola vez y distingue **ausencia total** (`None`) de
  **valor vacío o solo espacios** (`""`, `"   "`):

  | Valor | Resultado |
  |---|---|
  | variable ausente | `SQLiteIncidentRepository(":memory:")` |
  | `sqlite:///:memory:` | `SQLiteIncidentRepository(":memory:")` |
  | `sqlite:///ruta` | `SQLiteIncidentRepository(ruta)` |
  | `postgresql://…` con resto no vacío | `PostgresIncidentRepository(dsn)` |
  | `""`, solo espacios | `ConfigurationError("CONFIG_DATABASE_URL_INVALIDA")` antes de abrir conexión |
  | `postgres://…`, `mysql://…`, `sqlite://`, `sqlite:///` | `ConfigurationError` |

  `resolve_database_path` se conserva como helper exclusivo de SQLite y aplica la misma regla de
  vacío. Los mensajes de error incluyen solo el esquema, nunca usuario, contraseña ni host.
- **Razón**: FR-006 y SC-007 exigen que un despliegue incompleto falle de forma explícita y no caiga
  a memoria en silencio; ADR-004 rechaza el alias `postgres://`. La lectura única en la fábrica
  mantiene el Principio IV y FR-007.
- **Alternativas consideradas**: (a) tratar `""` como ausencia: pierde datos en silencio, justo lo
  que la clarificación prohíbe; (b) aceptar `postgres://`: contradice ADR-004; (c) seleccionar el
  motor en cada adaptador de entrada: duplicaría la interpretación del DSN. Se descartan.
- **Impacto en pruebas existentes**: `resolve_database_path("")` y
  `create_repository("postgresql://…")` cambian de resultado; las pruebas de H002 se actualizan para
  reflejar el contrato de H004.

## D5 · Uso de `INSERT ... ON CONFLICT DO UPDATE` y conflicto de alta

- **Decisión**: la **siembra idempotente de `sla_policies`** usa
  `INSERT ... ON CONFLICT (severity) DO UPDATE SET max_resolution_minutes = EXCLUDED.…,
  operates_24x7 = EXCLUDED.…`. La **ruta de alta de incidentes** usa `INSERT` estricto de una sola
  sentencia y traduce la violación de unicidad (`sqlstate 23505` / `psycopg.errors.UniqueViolation`)
  a `IncidentAlreadyExistsError`. No existe ningún `UPSERT` sobre `incidents`.
- **Razón**: el adaptador SQLite ya siembra políticas con `INSERT OR REPLACE`, que no es la ruta de
  negocio; su equivalente semántico en PostgreSQL es `ON CONFLICT DO UPDATE`. La Constitución
  (aclaración 1.2.1) y ADR-004 prohíben `REPLACE`, `UPSERT` y `ON CONFLICT DO UPDATE` **en la ruta de
  alta** para impedir sobrescrituras silenciosas; la siembra de políticas queda fuera de esa ruta,
  igual que la siembra sintética del benchmark. Esta lectura se documenta aquí y se cubre con una
  prueba de conflicto que verifica que el incidente previo no se modifica.
- **Alternativas consideradas**: (a) `ON CONFLICT DO NOTHING` en la siembra: no actualizaría una
  política cambiada y divergiría del `INSERT OR REPLACE` de SQLite; (b) borrar e insertar políticas:
  dos sentencias y una ventana sin política; (c) pre-consultar y decidir en Python: carrera y más
  viajes. Se descartan.
- **Trazabilidad**: la decisión requiere la aclaración PATCH 1.2.1 de la Constitución (PR separado) y
  no modifica ADR-004; se registra aquí y en el PR.

## D6 · Mapeo fila → entidad, validación y duplicación deliberada

- **Decisión**: el adaptador PostgreSQL replica la validación de invariantes de escritura y el mapeo
  `dict_row → Incident` dentro de su propio módulo, sin importar
  `src.adapters.outbound.sqlite_repository`. Usa `dict_row`, columnas explícitas y
  `datetime.fromisoformat`; no ordena resultados ni calcula SLA, similitud ni claves de grupo.
- **Razón**: ADR-004 §4 acepta explícitamente "dos DDL, dos mapeos y dos juegos de consultas" y
  prohíbe que un adaptador importe a otro para reutilizar lógica. La paridad se demuestra con la
  suite de contrato, no acoplando implementaciones. El Principio I impide además que el adaptador
  redeclare reglas de dominio: la validación replica invariantes del modelo ya existentes, no reglas
  nuevas.
- **Alternativas consideradas**: (a) extraer un módulo común `outbound/incident_rows.py`: reduce
  duplicación, pero introduce un acoplamiento que ADR-004 no contempla y amplía el alcance del hito;
  (b) mapear en la aplicación: viola el Principio III. Se descartan.
- **Columnas explícitas**: se reutiliza el mismo conjunto de diez columnas que SQLite
  (`incident_id, title, component, severity, status, created_at, resolved_at, raw_text,
  recommended_team, duplicate_group_key`) y el mismo `INNER JOIN sla_policies` en las consultas de
  lectura que hoy lo usan.

## D7 · Formato temporal persistido: microsegundos en ambos motores

- **Decisión**: normalizar `created_at` y `resolved_at` con
  `datetime.isoformat(timespec="microseconds")` en **ambos** adaptadores antes de escribir, y leer con
  `datetime.fromisoformat`. Las columnas siguen siendo `TEXT` y nunca `TIMESTAMP`/`TIMESTAMPTZ`, época
  numérica ni `now()` del motor; la sesión no se configura con zona porque nunca se genera ni se
  interpreta un instante en el servidor.
- **Razón**: FR-009 y el "Contrato de persistencia entre motores" de la Constitución exigen
  `YYYY-MM-DDTHH:MM:SS.ffffff` en ambos motores. Hoy SQLite escribe `isoformat()` sin forzar
  microsegundos; el cambio es localizado, no altera los `datetime` leídos ni los documentos de la API
  (Python omite la parte fraccionaria cuando es cero) y elimina una divergencia real entre motores.
- **Alternativas consideradas**: (a) dejar SQLite como está y formatear solo PostgreSQL: incumple la
  Constitución y produce textos distintos para el mismo instante; (b) usar `TIMESTAMP` en PostgreSQL:
  introduce zona y aritmética del motor, prohibido; (c) guardar época numérica: rompe el orden
  lexicográfico y la paridad. Se descartan.
- **Verificación**: una prueba de contrato compara el texto crudo persistido en ambos motores contra
  el patrón `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}$`.

## D8 · `GET /health`: 200/503, cuerpo exacto y sin caché

- **Decisión**: la ruta devuelve `JSONResponse` con `status_code` 200 o 503, `media_type`
  `"application/json"` y cabecera `Cache-Control: no-store` en ambos casos, usando
  `HealthResponse` como `response_model` y documentando 503 en `responses`. Ningún manejador nuevo de
  excepciones interviene: la ruta no lanza. Se actualiza la versión de la aplicación a `0.4.0`.
- **Razón**: FR-001/FR-002 y SC-002 exigen cuerpos exactos y que una caída nunca sea 500; la
  cabecera evita respuestas viejas en intermediarios (caso límite de la spec). Un `JSONResponse`
  permite fijar el estado sin introducir una excepción de dominio para la indisponibilidad.
- **Alternativas consideradas**: (a) `raise HTTPException(503)`: pasa por el manejador genérico y
  produce `application/problem+json`, no el documento de salud exigido; (b) `response.status_code =
  503` con el modelo: FastAPI no garantiza el cuerpo si hay `response_model` y complica el tipado;
  (c) un endpoint separado `/ready`: fuera de alcance por clarificación. Se descartan.
- **Compatibilidad**: `tests/adapters/test_api.py::test_health_responde_ok` espera hoy
  `{"status": "ok"}`; se actualiza al contrato nuevo.

## D9 · Códigos de salida y error de configuración en la consola

- **Decisión**: `cli health` imprime en **stdout** el documento de `HealthResponse` con
  `json.dumps(..., ensure_ascii=False, indent=2)` y termina `0` si `connected`, `1` si
  `unavailable`. Si `build_incident_service()` lanza `ConfigurationError`, imprime en **stderr** un
  `application/problem+json` con código `CONFIG_DATABASE_URL_INVALIDA`, campo `DATABASE_URL` y estado
  422, y termina `2`, sin documento de salud ni traza. Un fallo inesperado se traduce al código
  defensivo `HEALTH_ERROR_INTERNO` (stderr, 500, salida 1) para no filtrar una traza.
- **Razón**: FR-003, FR-018 y las clarificaciones exigen separar resultado (stdout) de error de
  configuración (stderr) y no añadir un `problem+json` en el caso de indisponibilidad. El código
  `CONFIG_DATABASE_URL_INVALIDA` se añade al catálogo de títulos de `problem.py`; el fallo interno es
  un borde defensivo del adaptador, no un estado operativo nuevo.
- **Alternativas consideradas**: (a) imprimir el documento de indisponibilidad también ante una
  configuración inválida: oculta un fallo de despliegue; (b) dejar propagar la excepción: Typer
  imprime traza, prohibido; (c) reutilizar `CREATE_ERROR_INTERNO`: confunde capacidades. Se
  descartan.
- **API**: si la configuración es inválida, `create_app()` falla al importar
  `build_incident_service()` y Uvicorn no arranca, que es el comportamiento exigido; el mensaje no
  incluye credenciales.

## D10 · Imagen de API: multietapa, `uv.lock`, usuario no root y healthcheck sin `curl`

- **Decisión**: `Dockerfile` multietapa sobre `python:3.12-slim`; etapa `builder` con la imagen
  oficial de `uv` fijada por etiqueta, `uv sync --frozen --no-dev --no-install-project` con
  `pyproject.toml`, `uv.lock` y `README.md`; etapa final con `.venv` y `src/`, usuario de sistema
  UID/GID 10001, `PATH` al entorno virtual y `CMD ["uvicorn",
  "src.adapters.inbound.api.app:app", "--host", "0.0.0.0", "--port", "8000"]`. El healthcheck de
  Compose usa `python -c` con `urllib.request` (la imagen slim no trae `curl`).
- **Razón**: FR-013 y RNF-007 exigen build reproducible desde el lockfile, sin cadena de compilación
  en runtime, sin root y sin credenciales. `--frozen` impide que la imagen resuelva versiones
  distintas a `uv.lock`; `--no-dev` deja fuera pytest, ruff y httpx.
- **Alternativas consideradas**: (a) `pip install -r requirements.txt`: no existe ni está fijado;
  (b) una sola etapa: arrastra cachés y herramientas de build; (c) `curl` para el healthcheck:
  añade un paquete innecesario o falla en slim; (d) `latest` para la imagen de uv: no reproducible.
  Se descartan.

## D11 · Compose: orden de arranque, volumen y credenciales de desarrollo

- **Decisión**: `docker-compose.yml` define `db` (`postgres:16-alpine`, volumen nombrado
  `incidentops_pgdata` sobre `PGDATA`, healthcheck `pg_isready`, sin `ports`) y `api`
  (`DATABASE_URL` apuntando a `db`, `depends_on: db: condition: service_healthy`, healthcheck sobre
  `/health`, puerto de host `${API_PORT:-8000}`, una réplica). Los valores de usuario, contraseña y
  base se interpolan desde el entorno con marcadores por defecto **explícitamente locales**
  (`incidentops`, `incidentops_local`); `.env.example` los documenta y `.env` sigue ignorado por Git.
- **Razón**: FR-014/FR-015 y RNF-011/SC-004 piden una sola orden desde un clon limpio y credenciales
  fuera de la imagen. Un `:?error` obligaría a crear `.env` antes de arrancar y rompería SC-004; los
  valores por defecto son marcadores de desarrollo, no secretos, y cualquier despliegue real los
  sobrescribe por entorno. La contraseña con caracteres especiales debe ir codificada en la URL y así
  se documenta. La base no se publica al host (RNF-008).
- **Alternativas consideradas**: (a) variables obligatorias: incumple "una sola orden"; (b)
  `POSTGRES_HOST_AUTH_METHOD=trust`: elimina la contraseña pero degrada la seguridad y no representa
  el contrato; (c) publicar `5432` para inspección: la spec lo deja como decisión explícita del
  operador, fuera del despliegue de referencia. Se descartan.
- **Persistencia**: `docker compose down` sin `-v` conserva el volumen; solo `down -v` lo elimina.

## D12 · `.dockerignore` mínimo y sin secretos

- **Decisión**: excluir `.git`, `.env`, `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`,
  `.mypy_cache`, `.opencode`, `.specify`, `tests/`, `specs/`, `docs/`, `data/`, `legacy/`, `*.db`,
  `*.log` y `CONTEXT_LOG.md`. Mantener `pyproject.toml`, `uv.lock`, `README.md` y `src/`.
- **Razón**: FR-016 y RNF-007 exigen una imagen mínima y reproducible; el contexto no debe contener
  credenciales, metadatos ni bases locales. Excluir `tests/` y `specs/` reduce tamaño y superficie.
- **Alternativas consideradas**: (a) ignorar solo `.venv` y `.git`: el contexto seguiría llevando
  bases y documentación; (b) `COPY . .`: impredecible y arriesgado. Se descartan.
- **Nota**: el build no recibe secretos por `ARG`; `DATABASE_URL` solo entra en ejecución.

## D13 · Estrategia de pruebas sin Docker y con PostgreSQL opcional

- **Decisión**:
  - `tests/test_spec_004_runtime_health.py` agrupa los escenarios BDD E-01…E-06 con dobles en
    memoria, `TestClient` y `CliRunner`, más la verificación estructural de `Dockerfile`,
    `.dockerignore`, `docker-compose.yml` y `.env.example` mediante lectura de texto y expresiones
    regulares (sin PyYAML).
  - `tests/adapters/test_factory.py` cubre la matriz de `DATABASE_URL`, el cumplimiento de
    `IncidentRepositoryPort` por ambos adaptadores y los errores de configuración.
  - `tests/contract/test_repository_contract.py` parametriza SQLite y PostgreSQL; el caso PostgreSQL
    se omite si no hay `TEST_POSTGRES_URL` o si `psycopg` no está disponible.
  - `tools/verify_runtime.py --compose [--resiliencia]` es la verificación manual/CI con Docker.
- **Razón**: RNF-001/RNF-013 exigen que la suite pase sin Docker, sin red y sin base real; C-02 y
  RNF-006 exigen la misma suite de contrato contra ambos motores. Las pruebas estructurales de Docker
  no dependen del daemon y detectan regresiones de configuración; la verificación real queda en el
  script explícito.
- **Alternativas consideradas**: (a) `testcontainers`: dependencia nueva y Docker obligatorio en la
  suite; (b) `PyYAML` para leer Compose: dependencia nueva innecesaria; (c) omitir la suite de
  contrato: la paridad quedaría sin evidencia. Se descartan.

## D14 · Fronteras Ruff para `psycopg` y el adaptador concreto

- **Decisión**: añadir a `src/adapters/inbound/ruff.toml` y
  `src/adapters/inbound/api/ruff.toml` las prohibiciones `psycopg`, `psycopg2` y
  `src.adapters.outbound.postgres_repository`, junto a las ya existentes para SQLite y el legado.
  Dominio y aplicación ya prohíben `psycopg`/`psycopg2`; el adaptador de salida no necesita
  `ruff.toml` propio.
- **Razón**: RNF-009 exige que `psycopg` solo pueda importarse desde `src/adapters/outbound/` y que
  `DATABASE_URL` solo se lea en la fábrica. La prohibición del módulo concreto evita que el inbound
  instancie el repositorio y conserve la composición única.
- **Alternativas consideradas**: confiar en revisión manual: el Principio VI exige verificación
  estática. Se descarta.
- **Evidencia**: `uv run ruff check src/` debe pasar con `TID251` activo y sin `noqa` nuevos.
