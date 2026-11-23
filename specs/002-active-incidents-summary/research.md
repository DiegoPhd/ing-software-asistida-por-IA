# Investigación · Resumen de Incidentes Activos (H002)

**Fecha**: 2026-11-22 | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

No quedan incógnitas marcadas como `NEEDS CLARIFICATION`. Cada decisión siguiente resuelve un punto técnico que el plan necesita antes de diseñar.

## D1 · Migración del cálculo de SLA al dominio

- **Decisión**: crear `src/domain/models.py` (`Incident`, `IncidentStatus`, `SLARule`, `SLAEvaluation`, resumen) y `src/domain/sla_calculator.py` (`SLA_POLICY_TABLE`, `get_sla_rule_for_severity`, `evaluate_sla_status`, `summarize_active_incidents`). Retirar `src/models.py`, `src/sla_calculator.py` y `src/incident_repository.py`.
- **Razón**: el usuario pide que el caso de uso calcule SLA con `src/domain/sla_calculator.py`, y ese módulo no existe: la implementación vigente está duplicada en `src/sla_calculator.py`, con copias de `Incident`, `SLARule`, `SLAEvaluation` y un `IncidentStatus` divergente. Mantener ambas rutas violaría el Principio I y la regla de retirar el punto de entrada anterior en el mismo PR.
- **Alternativas consideradas**: (a) importar el legado desde el servicio: la aplicación conocería tipos fuera del dominio y quedarían dos definiciones; (b) dejar el legado como fachada de reexportación: conserva el punto de entrada `python -m src.sla_calculator` y dos formas de invocar la capacidad. Se descartan.
- **Inmutabilidad**: `SLA_POLICY_TABLE` se publica como `Mapping` inmutable (`MappingProxyType`) para no introducir estado global mutable en el dominio; el adaptador lo recorre con `.values()` al sembrar políticas.
- **Ajuste funcional documentado**: `requires_escalation` exige estado activo (`OPEN`, `IN_PROGRESS`). El código legado solo excluía `RESOLVED`, de modo que un `CLOSED` podía escalar; la Constitución prohíbe escalar en estados terminales. No altera el resumen (solo incluye activos), pero corrige la regla del dominio.

## D2 · El resumen se calcula en el dominio

- **Decisión**: `src/domain/sla_calculator.py` expone `summarize_active_incidents(incidents, reference_time) -> ActiveIncidentsSummary`, con `ActiveIncidentsSummary(total_active, breached_count, incidents)` y `ActiveIncidentDetail(incident, evaluation)`. El orden (severidad, minutos descendentes, identificador ascendente) y los totales se resuelven allí.
- **Razón**: contar incumplimientos y ordenar el detalle son reglas del negocio; si viven en el servicio, la aplicación deja de ser orquestación pura (Principio III/IV) y la paridad depende de que cada adaptador repita el orden.
- **Alternativas consideradas**: (a) totales en el servicio y orden en cada adaptador: duplica contrato y arriesga divergencia; (b) orden en SQL: ata una regla de presentación al motor y no cubre el orden por minutos de SLA, que se calculan en el dominio.

## D3 · Puerto de repositorio y verificación estructural

- **Decisión**: `src/application/ports.py` declara `IncidentRepositoryPort` como `Protocol` marcado `@runtime_checkable`, con `save_incident`, `get_incident`, `find_open_duplicates`, `list_active_incidents` y `check_health`. La prueba compara nombres de métodos, parámetros y tipos de retorno mediante `inspect.signature`, además de `isinstance`.
- **Razón**: `Protocol` no hereda ni obliga en ejecución; el usuario exige una verificación de cumplimiento como parte de la entrega. `runtime_checkable` solo comprueba presencia de métodos, por eso la prueba inspecciona también las firmas.
- **Alternativas consideradas**: (a) heredar de `abc.ABC`: acopla el adaptador a la aplicación y contradice ADR-003; (b) confiar solo en `mypy`: no está configurado y añadiría una dependencia y una puerta nuevas; (c) `isinstance` sin firmas: aceptaría un método con parámetros equivocados.
- **Alcance de `find_open_duplicates`**: en H002 devuelve candidatos activos del mismo componente y distinto identificador. La similitud y la ventana por severidad son de H003; la firma se mantiene estable para no romper el puerto después.

## D4 · SQL optimizado y esquema SQLite

- **Decisión**: una sola consulta con `INNER JOIN sla_policies` sobre `incidents`, filtro de estado en SQL, filtro opcional por componente y columnas explícitas. Índice `idx_incidents_component_status (component, status)` creado con `CREATE INDEX IF NOT EXISTS`. Se siembran las políticas desde `SLA_POLICY_TABLE` del dominio.
- **Razón**: el `INNER JOIN` descarta incidentes cuya severidad no tiene política vigente y evita reconstruir filas que el dominio no sabría evaluar; el índice compuesto sirve al filtro más selectivo (`component` + `status`), que es el caso de la interfaz. Una sola consulta elimina el N+1 y el `SELECT *`.
- **Alternativas consideradas**: (a) dos consultas (incidentes + políticas en lote): añade ida y vuelta y mapeo conjunto sin beneficio para una tabla de cuatro filas; (b) índice solo por `status`: baja selectividad (dos valores) y no ayuda al filtro por componente; (c) `INNER JOIN` con subconsulta por severidad: reproduce el N+1 de forma encubierta.
- **Conteo de consultas**: la prueba envuelve el cursor del repositorio y afirma que el resumen emite exactamente una consulta después del esquema. Es una verificación objetiva del cierre del N+1, independiente del tiempo de ejecución.

## D5 · Raíz de composición y `DATABASE_URL`

- **Decisión**: `src/adapters/outbound/factory.py` expone `build_incident_service(database_url: Optional[str] = None)` y `create_repository(...)`. Lee `DATABASE_URL` (por defecto `sqlite:///:memory:`) y rechaza esquemas distintos de `sqlite` con un error claro. `src/composition.py` se retira y los adaptadores de entrada importan la fábrica.
- **Razón**: el inbound no puede conocer drivers ni repositorios concretos; la selección por DSN es un detalle de salida. Dejar `composition.py` y `factory.py` como ensambladores alternativos produciría dos formas competidoras de construir el servicio.
- **Alternativas consideradas**: (a) mantener `composition.py` como ensamblador y pasar la URL desde el borde: el inbound seguiría eligiendo o construyendo persistencia; (b) fábrica que solo devuelve la clase y composición que la instancia: la lógica de selección queda partida en dos módulos y la fábrica instancia de todos modos.
- **Consecuencia de gobernanza**: la Constitución §IV ya nombra `src/adapters/outbound/factory.py` como único punto de ensamblaje y fija `IncidentRepositoryPort` como puerto vigente de H002. La enmienda MINOR 1.1.0 y el ADR-005 quedan registrados en el mismo PR.
- **Frontera estática**: el `ruff.toml` del inbound prohíbe `src.adapters.outbound.sqlite_repository` y permite únicamente `src.adapters.outbound.factory`; el prefijo genérico `sqlite` no cubriría el nombre real del módulo.

## D6 · Contrato de transporte compartido

- **Decisión**: `src/adapters/inbound/summary_contract.py` define `ActiveIncidentItem`, `ActiveIncidentsSummaryResponse` (Pydantic v2) y `to_summary_response(summary)`. HTTP lo usa como `response_model`; CLI lo serializa con `model_dump` envuelto en `json.dumps`.
- **Razón**: los nombres y tipos de los campos quedan en un solo lugar y la paridad se prueba comparando el mismo documento. Compartir el contrato no es acoplar dos adaptadores concretos, igual que `problem.py` comparte el documento de error en H001; el CLI no importa nada de `api/`.
- **Alternativas consideradas**: (a) `asdict` del resultado de dominio en la CLI y esquema aparte en REST: dos mapeos y dos posibles nombres; (b) importar `api/schemas.py` desde la CLI: dependencia entre adaptadores concretos, prohibida por la skill; (c) serializar el dominio directamente: filtra la forma interna al contrato público.
- **Campos**: `total_active`, `breached_count`, `incidents[]`; por ítem, `incident_id`, `title`, `component`, `severity`, `status`, `elapsed_minutes`, `is_breached`, `requires_escalation`. `is_breached` permite que el total sea verificable contra el detalle (SC-004).

## D7 · Instante de referencia y validación

- **Decisión**: `reference_time` opcional, ISO 8601 sin zona horaria. HTTP lo recibe como query param de texto y la CLI como `--reference-time`; ambos usan el mismo validador de `summary_contract.py`, de modo que una fecha mal formada o con zona produce el mismo código en los dos canales (`SUMMARY_REFERENCIA_INVALIDA`). El servicio usa `datetime.now()` si se omite. Se rechazan filtros de componente de más de 128 caracteres (`SUMMARY_COMPONENTE_DEMASIADO_LARGO`) y datos incoherentes con `created_at` posterior al instante (`SUMMARY_REFERENCIA_INCONSISTENTE`, HTTP 409).
- **Razón**: el dominio exige fechas naive consistentes y un instante único por respuesta; aceptar zonas abriría comparaciones `offset-naive` vs `offset-aware`. El 409 distingue un dato corrupto de una petición mal formada (422).
- **Alternativas consideradas**: (a) normalizar a UTC: cambia la semántica de las fechas almacenadas y exige migración de datos; (b) rechazar toda petición sin `reference_time`: rompe la consulta operativa normal; (c) usar 422 para la incoherencia: confunde la causa y sugiere que el cliente puede corregir el dato.
- **CLI**: `--reference-time` (con guion) sigue la convención de `--incident-id` y `--raw-text`; el borrador `--referencetime` se descarta por consistencia. El valor por defecto es el instante actual.

## D8 · Simulación de dobles y aislamiento de pruebas

- **Decisión**: dominio y caso de uso usan `SQLiteIncidentRepository(":memory:")` inyectado; las pruebas de paridad usan una base de archivo temporal y `DATABASE_URL` apuntando a ella, de modo que la app y la CLI abren el mismo dato.
- **Razón**: `:memory:` es privado por conexión; dos procesos o dos conexiones verían bases distintas y la paridad fallaría por infraestructura, no por contrato. El archivo temporal permite sembrar una vez y consultar desde ambos canales, y se elimina al terminar la prueba.
- **Alternativas consideradas**: (a) URL de memoria compartida (`file:...mode=memory&cache=shared`): funciona pero exige mantener viva una conexión ancla y complica el ciclo de vida; (b) doble en memoria del puerto para la paridad: no probaría el adaptador SQLite ni el índice; (c) base compartida global: acopla pruebas y deja estado entre escenarios.
- **Concurrencia**: el repositorio abre una conexión con `check_same_thread=False` y serializa operaciones con `threading.Lock`, porque el `TestClient` ejecuta el endpoint síncrono en otro hilo.

## D9 · Verificación de rendimiento

- **Decisión**: validar con `EXPLAIN QUERY PLAN` que la consulta filtrada usa `idx_incidents_component_status`, contar las consultas emitidas, medir el resumen de 10.000 filas con el benchmark `python -m src.adapters.outbound.sqlite_repository --records 10000` y medir el mismo resumen por HTTP y CLI con `tools/benchmark_summary.py`.
- **Razón**: una aserción de tiempo en CI es frágil (máquina, carga, intérprete) y no demuestra la causa de la mejora. El plan de consulta y el conteo prueban la propiedad que H002 introduce; el tiempo se reporta como evidencia en el PR frente a `SC-001`.
- **Alternativas consideradas**: (a) `assert elapsed < 1` en pytest: puede fallar por ruido y no distingue regresión de entorno; (b) solo benchmark manual: no protege contra la reaparición del N+1; se combinan ambas.

## D10 · Nombres del dominio

- **Decisión**: los módulos nuevos usan los nombres canónicos `models.py` y `sla_calculator.py`. `src/domain/triage.py` es el nombre canónico del triaje de H001 y la Constitución se corrige para reflejarlo; `legacy/triage_rules.py` permanece congelado.
- **Razón**: el hito migra la capacidad de SLA, no la de triaje; renombrar el módulo de H001 obligaría a tocar su contrato y sus pruebas sin aportar valor a H002. La Constitución se cumple por responsabilidad y unicidad, no por renombrar archivos existentes.
- **Alternativas consideradas**: renombrar `triage.py` a `triage_rules.py` en este PR: alcance no solicitado y riesgo de romper la spec 001. Se descarta; la Constitución se alinea con el nombre real del módulo.

## D11 · Errores y códigos estables

- **Decisión**: añadir títulos y códigos al documento compartido: `SUMMARY_COMPONENTE_DEMASIADO_LARGO`, `SUMMARY_REFERENCIA_INVALIDA`, `SUMMARY_SOLICITUD_INVALIDA`, `SUMMARY_REFERENCIA_INCONSISTENTE`, `SUMMARY_ERROR_INTERNO`. El manejador de esquema elige el prefijo según la ruta; el de errores inesperados no expone detalles internos.
- **Razón**: la spec exige códigos estables y paridad de error; los códigos `TRIAGE_*` no describen una consulta de resumen. El prefijo por ruta conserva el contrato de H001 sin duplicar manejadores.
- **Alternativas consideradas**: reutilizar `TRIAGE_SOLICITUD_INVALIDA` en el resumen: comunica mal el dominio y confunde a los clientes; un manejador por endpoint: duplica el formato problem+json y arriesga divergencia.
