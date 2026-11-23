# Investigación · Ciclo de vida, duplicados y SLA (H003)

**Fecha**: 2026-11-22 | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

No quedan incógnitas marcadas como `NEEDS CLARIFICATION`. Cada decisión siguiente resuelve un punto
técnico que el plan necesita antes de diseñar. Las cuatro clarificaciones de la spec (instante de
creación, original más antiguo, SLA de un terminal y concurrencia) se toman como cerradas.

## D1 · Campos nuevos de `Incident` y nombre del tipo de equipo

- **Decisión**: ampliar `src/domain/models.py` con `Incident.recommended_team: Optional[Team] = None`
  y `Incident.duplicate_group_key: Optional[str] = None`, añadidos al final del `dataclass` para no
  romper las construcciones posicionales existentes. El tipo es `Team`, el `Literal` del catálogo
  cerrado de `src/domain/severity.py`, no un alias nuevo `TeamName`.
- **Razón**: la spec y la Constitución §I nombran `Incident`, `Team` y `duplicate_group_key`; crear un
  alias `TeamName` produciría dos nombres para el mismo catálogo cerrado, lo que el Principio I
  prohíbe. Los valores por defecto `None` preservan la compatibilidad con H001/H002 y con las filas
  históricas que no traen equipo ni clave de grupo.
- **Alternativas consideradas**: (a) hacer los campos obligatorios: rompe `tests/domain`,
  `test_sqlite_repository` y las bases heredadas sin migración de datos; (b) declarar un `StrEnum`
  nuevo para equipos: exigiría enmienda y pruebas de aceptación del catálogo, fuera del alcance del
  hito; (c) guardar el equipo solo en el DTO: impediría que la consulta de SLA y el resumen de H002
  lo informen desde el almacenamiento.
- **Consecuencia**: el mapeo fila → entidad valida que un `recommended_team` no nulo pertenezca a
  `COMPONENT_TEAM.values()`; un valor desconocido en la base es `InvalidIncidentError` (dato
  incoherente), no un valor por defecto inventado.

## D2 · Normalización temporal naive/aware en `sla_calculator.py`

- **Decisión**: sustituir el `_validar_naive` privado por una pareja de funciones puras y
  reutilizables: `validar_instante_naive(instante, campo)` y
  `resolver_ventana_temporal(incident, reference_time) -> (created_at, end_time, window)`. Reglas:
  1. `created_at`, `resolved_at` y `reference_time` deben ser naive; un aware se rechaza con
     `TemporalInconsistencyError` (nunca se convierte a UTC).
  2. `reference_time >= created_at` **siempre**, también para incidentes terminales (FR-022).
  3. Si el estado es terminal, `resolved_at` es obligatorio y `resolved_at >= created_at`; si no,
     `InvalidIncidentError` (dato incoherente, no entrada del cliente).
  4. `end_time = resolved_at or reference_time`; en terminales el cómputo queda congelado aunque
     `reference_time` sea anterior a la resolución (clarificación de la spec).
  5. `window = "24x7"` si `SLARule.operates_24x7`, `"BUSINESS_HOURS"` en caso contrario.
- **Razón**: hoy `evaluate_sla_status` calcula `end_time = resolved_at or reference_time` y solo
  compara `end_time < created_at`; con un terminal, una referencia anterior a la creación pasa
  inadvertida porque `end_time` es la resolución. FR-022 exige rechazarla. Centralizar la validación
  evita que resumen, auditoría y alta apliquen reglas temporales distintas.
- **Alternativas consideradas**: (a) normalizar aware a UTC o a la zona local: cambia la semántica de
  los datos almacenados, exige migración y contradice la restricción "fechas naive consistentes"; (b)
  aceptar aware cuando `tzinfo.utcoffset() is None` (`ZoneInfo` sin offset resuelto): deja pasar
  valores ambiguos; (c) validar solo en los adaptadores: repetiría la regla en dos canales y el
  dominio seguiría pudiendo mezclar tipos.
- **Impacto en H002**: `summarize_active_incidents` ya rechaza `created_at > reference_time` antes de
  evaluar, así que sus valores no cambian; la prueba de la frontera temporal sigue en verde.

## D3 · Evaluación de SLA con contexto

- **Decisión**: añadir a `src/domain/models.py` `SLAComputationWindow = Literal["24x7",
  "BUSINESS_HOURS"]` y
  `SLAEvaluationDetail(incident, evaluation, reference_time, window)`, ambos `frozen=True`. Añadir
  `evaluate_sla_detail(incident, reference_time) -> SLAEvaluationDetail` en `sla_calculator.py`, que
  usa `resolver_ventana_temporal`, llama a `evaluate_sla_status` y adjunta la ventana.
- **Razón**: FR-018 pide `incident_id`, `severity`, `status`, `created_at`, `resolved_at`,
  `reference_time` y la ventana aplicada, además de los valores ya calculados. Ampliar
  `SLAEvaluation` con esos campos obligaría a tocar el resumen de H002 y su contrato; un tipo nuevo
  que lo compone mantiene el cálculo existente y su tabla de pruebas.
- **Alternativas consideradas**: (a) ampliar `SLAEvaluation`: rompe el contrato de H002 y la
  construcción del resumen; (b) devolver una tupla o un `dict` desde el servicio: pierde tipos y
  traslada nombres de campos al borde; (c) calcular la ventana en el DTO: duplicaría una regla de la
  política en el adaptador.
- **Ventana como texto**: se expone como valor enumerado (`24x7` / `BUSINESS_HOURS`) y no como
  horario legible, porque la representación legible ("L-V 08:00-18:00") es presentación y pertenece
  al contrato de transporte si se necesita.

## D4 · Detección de equivalencia en el dominio

- **Decisión**: implementar en `src/domain/triage_rules.py`:
  `DUPLICATE_SIMILARITY_THRESHOLD = 0.75`,
  `DUPLICATE_WINDOW_DAYS: Mapping[SeverityLevel, int] = MappingProxyType({"P0": 1, "P1": 2, "P2": 3,
  "P3": 4})`, `DuplicateAssessment(duplicate_group_key, duplicate_of)` con propiedad
  `is_duplicate`, `is_equivalent(older, newer)` y
  `assess_duplicates(new_incident, candidates)`.
- **Reglas implementadas**:
  - Candidato válido: estado en `ACTIVE_STATUSES`, mismo `component`, distinto `incident_id` y
    `raw_text` no vacío.
  - Similitud: `SequenceMatcher(None, nuevo.lower(), candidato.lower()).ratio() >= 0.75`; el umbral
    exacto es equivalente y un valor inmediatamente inferior no lo es.
  - Ventana: `0 <= delta <= timedelta(days=DUPLICATE_WINDOW_DAYS[severidad_del_más_antiguo])`,
    tomando como más antiguo el de la clave canónica `(created_at, incident_id)` menor. El límite
    exacto (`== ventana`) es candidato.
  - `duplicate_of`: solo equivalentes **previos** en el orden canónico, ordenados de más antiguo a
    más reciente y, en empate, por identificador ascendente.
  - `duplicate_group_key`: `None` si no hay previos; si hay, `original.duplicate_group_key or
    original.incident_id` del más antiguo.
- **Razón**: el Principio I asigna "detección de duplicados" a `triage_rules.py`; la similitud de
  texto y la ventana por severidad son reglas de negocio, no filtros de almacenamiento. Un futuro
  adaptador PostgreSQL debe heredar la misma decisión sin reimplementarla.
- **Alternativas consideradas**: (a) `LIKE` o comparación en SQL: SQLite no calcula `SequenceMatcher`
  y el umbral quedaría fuera del dominio; (b) heredar la clave de cualquier duplicado en lugar del
  original: la Constitución exige la clave del original más antiguo; (c) ventana según la severidad
  del nuevo: la spec fija la del más antiguo del par.
- **Determinismo**: la comparación es estable; `difflib` está permitido en el dominio por la skill y
  no depende de reloj, red ni entorno.

## D5 · Alcance de `find_open_duplicates` en el puerto y el adaptador

- **Decisión**: conservar la firma `find_open_duplicates(incident: Incident) -> Sequence[Incident]`
  de H002 y su semántica estructural (activos, mismo componente, identificador distinto). El
  adaptador devuelve las columnas nuevas y el dominio aplica similitud y ventana. No se añade
  parámetro de ventana ni de umbral al puerto.
- **Razón**: la firma se mantuvo estable en H002 precisamente para H003. Pasar umbral o ventana al
  adaptador convertiría el puerto en un contrato de regla de negocio y permitiría que dos adaptadores
  discrepen. El filtro estructural ya reduce el conjunto al componente, que es el índice disponible.
- **Alternativas consideradas**: (a) filtrar por ventana en SQL usando la severidad del nuevo: la
  regla depende de la severidad del más antiguo del par y puede incluir candidatos posteriores, con
  lo que el prefiltro sería incorrecto; (b) devolver todos los incidentes y filtrar en el servicio:
  trasladaría una regla del dominio a la aplicación.
- **Rendimiento**: con el catálogo cerrado de seis componentes, el subconjunto por componente es una
  fracción acotada de los 10.000 activos; el adaptador no añade consultas por fila.

## D6 · Escritura del alta: conflicto, atomicidad y siembra

- **Decisión**: `save_incident` usa `INSERT` estricto sobre la clave primaria y traduce
  `sqlite3.IntegrityError` a `IncidentAlreadyExistsError` (definida en `src/application/services.py`,
  importable por el adaptador). La validación de invariantes del incidente se mantiene antes de
  escribir. El seeder sintético del benchmark conserva una sentencia idempotente propia.
- **Razón**: FR-008 prohíbe sobrescribir, fusionar o alterar el incidente previo; `INSERT OR REPLACE`
  lo hacía en silencio. El `INSERT` es una sola sentencia atómica (FR-016). Que el adaptador traduzca
  el error del driver mantiene el código estable en la aplicación, que es quien lo publica.
- **Alternativas consideradas**: (a) pre-consultar `get_incident` en el servicio: carrera entre
  comprobación e inserción y una lectura extra por alta; (b) `save_incident` devolviendo `bool`: el
  servicio tendría que inventar el error y el puerto mezclaría consulta y comando; (c) capturar
  `sqlite3.IntegrityError` en el servicio: la aplicación conocería el driver, prohibido por el
  Principio III.
- **Migración de bases heredadas**: `_init_schema` comprueba `PRAGMA table_info(incidents)` y añade
  `recommended_team` y `duplicate_group_key` si faltan, con el mismo patrón idempotente que ya usa
  para `raw_text`.

## D7 · Serialización por componente y concurrencia

- **Decisión**: `IncidentService` mantiene un registro de `threading.Lock` por componente, protegido
  por un cerrojo de guarda, y ejecuta bajo él la secuencia `find_open_duplicates → assess_duplicates
  → save_incident`. El cerrojo es de proceso y no se comparte entre réplicas. `create_incident`
  acepta un `now: Optional[Callable[[], datetime]]` en el constructor del servicio para inyectar el
  reloj en pruebas.
- **Razón**: FR-030 pide que dos altas equivalentes del mismo componente se serialicen y que la
  segunda vea a la primera; el supuesto de la spec limita la garantía a un almacenamiento único, sin
  bloqueo distribuido. La aplicación puede secuenciar y transaccionar (Principio IV) y el cerrojo no
  contiene reglas de negocio.
- **Alternativas consideradas**: (a) `BEGIN IMMEDIATE` en el adaptador abarcando detección y alta:
  obligaría a que el adaptador decidiera equivalencia o a exponer una transacción con callback al
  dominio, acoplando capas; (b) puerto `ComponentLockPort`: un `Protocol` con una sola
  implementación y sin otro llamador, abstracción especulativa que la Constitución §IV no exige; (c)
  aceptar la carrera: incumple SC-010 y la clarificación de la spec.
- **Límite documentado**: dos procesos distintos sobre el mismo archivo no comparten el cerrojo. La
  clave primaria sigue evitando sobrescrituras y el supuesto de la spec excluye réplicas; ADR-006 lo
  registra como trade-off.
- **Desempate en el escenario concurrente**: el veredicto depende del orden canónico
  `(created_at, incident_id)`. La prueba de dos hilos fija el `created_at` del segundo registro
  posterior al primero (o un identificador canónicamente mayor a igual instante), de modo que la
  aserción "el segundo informa al primero" sea determinista y no dependa del planificador.

## D8 · Traducción de errores: 422 incoherente y 404

- **Decisión**: `DataInconsistencyError` gana un atributo `status: int = 409` (retrocompatible). El
  manejador HTTP usa `exc.status`; la CLI mantiene salida `1` para toda incoherencia de datos.
  `IncidentNotFoundError` se traduce a `404` en HTTP y salida `1` en CLI. Se añaden los códigos
  `CREATE_*` y `SLA_*` y el prefijo de error se elige por ruta.
- **Razón**: FR-022 exige `422` para `reference_time < created_at` con salida `1`; el resumen de H002
  usa `409` para su propia incoherencia y no debe cambiar. Un único manejador con estado
  parametrizado evita duplicar el documento problem+json y conserva el código estable.
- **Alternativas consideradas**: (a) nueva excepción `TemporalReferenceError` con su manejador:
  duplica la forma del error y obliga a tocar ambos adaptadores; (b) devolver 409 también en el SLA:
  contradice FR-022 y la tabla de interfaces; (c) 404 con 422: confunde "no existe" con "entrada
  inválida" y rompe FR-023.
- **Prefijos**: `CREATE_*` para `POST /api/v1/incidents` y `SLA_*` para `.../{id}/sla`; `TRIAGE_*` y
  `SUMMARY_*` se conservan para H001/H002. La ruta `/summary` debe evaluarse antes que el patrón
  `/incidents/{id}/sla` al elegir prefijo, aunque ambas son distinguibles por sufijo.

## D9 · Contrato de transporte compartido y formatos de fecha

- **Decisión**: `src/adapters/inbound/temporal_contract.py` expone `PATRON_INSTANTE` y
  `parse_instante_naive(valor, campo, codigo)`; `summary_contract.parse_reference_time` delega en él
  con `SUMMARY_REFERENCIA_INVALIDA` sin cambiar su comportamiento.
  `src/adapters/inbound/lifecycle_contract.py` define `CreateIncidentRequest`,
  `IncidentCreatedResponse`, `SLAEvaluationResponse`, los mapeos desde el dominio y un
  `derivar_titulo(raw_text)` determinista. HTTP los usa como `response_model`; la CLI los serializa
  con `model_dump(mode="json")`.
- **Razón**: la paridad exige nombres y tipos en un solo lugar y el CLI no puede importar `api/`.
  `model_dump(mode="json")` produce la misma cadena ISO que Pydantic en HTTP; con `json.dumps` sobre
  `model_dump()` las fechas no son serializables y con `asdict` los nombres podrían divergir.
- **Alternativas consideradas**: (a) duplicar los modelos en `api/schemas.py` y en la CLI: dos
  contratos y deriva de nombres; (b) importar `api/schemas.py` desde la CLI: dependencia entre
  adaptadores concretos prohibida por la skill y por Ruff; (c) reutilizar `TriageResponse` para el
  alta: no incluye estado, fechas ni aviso de duplicados.
- **`extra="forbid"`**: los tres DTOs de entrada rechazan campos desconocidos (FR-029); FastAPI los
  convierte en `RequestValidationError` y el manejador los publica como `422` con código
  `CREATE_SOLICITUD_INVALIDA` o `SLA_SOLICITUD_INVALIDA`.
- **Título derivado**: primera línea del texto recortada, hasta 200 caracteres; si queda vacía se usa
  el texto recortado. Determinista y estable, sin reloj ni aleatoriedad.
- **Validación de `created_at` y `reference_time`**: el parser del borde rechaza espacio en lugar de
  `T`, zona horaria, formatos distintos y tipos no textuales; el dominio vuelve a comprobar naive
  porque es la última frontera antes de la aritmética.

## D10 · Catálogo de errores estables

- **Decisión**:

  | Código | HTTP | CLI | Causa |
  |---|---:|---:|---|
  | `CREATE_ID_VACIO` | 422 | 2 | Identificador vacío o solo espacios |
  | `CREATE_ID_DEMASIADO_LARGO` | 422 | 2 | Identificador > 64 caracteres |
  | `CREATE_TEXTO_VACIO` | 422 | 2 | Texto vacío o solo espacios |
  | `CREATE_TEXTO_DEMASIADO_LARGO` | 422 | 2 | Texto > 10 000 caracteres |
  | `CREATE_TITULO_VACIO` / `CREATE_TITULO_DEMASIADO_LARGO` | 422 | 2 | Título indicado inválido |
  | `CREATE_CREACION_INVALIDA` | 422 | 2 | `created_at` malformado o con zona |
  | `CREATE_SOLICITUD_INVALIDA` | 422 | 2 | Campo desconocido o cuerpo no conforme |
  | `CREATE_ID_CONFLICTO` | 409 | 1 | Identificador ya almacenado |
  | `CREATE_ERROR_INTERNO` | 500 | 1 | Fallo inesperado del alta |
  | `SLA_ID_VACIO` | — (sólo CLI) | 2 | Identificador vacío en el comando |
  | `SLA_REFERENCIA_INVALIDA` | 422 | 2 | `reference_time` malformado o con zona |
  | `SLA_SOLICITUD_INVALIDA` | 422 | 2 | Parámetro desconocido o repetido |
  | `SLA_REFERENCIA_INCONSISTENTE` | 422 | 1 | Referencia anterior a la creación |
  | `SLA_DATOS_INCONSISTENTES` | 409 | 1 | Severidad/estado desconocidos o `resolved_at < created_at` |
  | `SLA_INCIDENTE_NO_ENCONTRADO` | 404 | 1 | Identificador sin incidente |
  | `SLA_ERROR_INTERNO` | 500 | 1 | Fallo inesperado de la auditoría |

- **Razón**: FR-028 exige indicar el campo y un mensaje comprensible con un código estable; la CLI y
  HTTP comparten el catálogo (FR-021) y los códigos describen la capacidad, no el framework.
- **Alternativas consideradas**: reutilizar `TRIAGE_*` para el alta (el alta no es triaje y añade
  persistencia y conflicto) y `SUMMARY_*` para el SLA de un incidente (el resumen es agregado, no
  puntual). Se descartan.

## D11 · Estrategia de pruebas y verificación de rendimiento

- **Decisión**: `tests/test_spec_003_lifecycle_sla.py` agrupa cinco bloques BDD con `TestClient` y
  `CliRunner` sobre una base de archivo temporal por prueba: (1) alta persistente y recuperación tras
  reinicio; (2) aviso de duplicados y ausencia de falsos positivos; (3) auditoría de SLA con sus
  fronteras; (4) paridad HTTP/CLI y errores estables; (5) casos límite, concurrencia y volumen. Las
  aserciones de tiempo quedan fuera de la suite: se reporta como evidencia el alta y la consulta con
  10.000 activos y el `EXPLAIN QUERY PLAN` del índice nuevo.
- **Razón**: el Principio VII exige escenarios ejecutables y el plan de H002 ya fijó que las
  aserciones de tiempo en CI son frágiles. La concurrencia se prueba con dos hilos y una barrera, no
  con `sleep`.
- **Alternativas consideradas**: (a) `assert elapsed < 1` en pytest: falla por ruido de la máquina;
  (b) un solo escenario "feliz" por historia: no cubre los casos límite que la spec enumera ni los
  criterios SC-002/SC-005/SC-010; (c) base en memoria para las pruebas de reinicio: cada conexión ve
  una base distinta y el escenario no probaría nada.
- **Pruebas unitarias complementarias**: dominio (`test_duplicate_rules.py` con similitud 0,74/0,75,
  ventana exacta y un segundo por encima, grupo heredado, candidato sin texto y posterior), SLA
  (aware rechazado, referencia anterior a creación, terminal congelado y coherencia de `resolved_at`)
  y adaptador (columnas nuevas, índice, conflicto de alta y candidatos estructurales).
