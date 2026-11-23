# Tareas: Resumen de Incidentes Activos (H002)

**Entrada**: Documentos de diseño de `specs/001-active-incidents-summary/`

**Prerrequisitos**: [plan.md](./plan.md) (obligatorio), [spec.md](./spec.md) (obligatorio), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Pruebas**: incluidas por mandato de `plan.md` (§Orden de implementación 7 y §Criterios de Cierre) y de la Constitución §3.2. En este hito no son opcionales: cada historia se valida con escenarios Dado/Cuando/Entonces.

**Organización**: las tareas se agrupan por historia de usuario para que cada una sea implementable, verificable y entregable por separado. La Fase 2 concentra el dominio, el puerto, el adaptador SQLite, la fábrica y el contrato compartido, porque las tres historias dependen de ellos.

## Formato: `[ID] [P?] [Story] Descripción`

- **[P]**: puede ejecutarse en paralelo (archivos distintos, sin dependencia de una tarea incompleta)
- **[Story]**: historia de usuario a la que pertenece la tarea (`US1`, `US2`, `US3`)
- Todas las descripciones incluyen la ruta exacta del archivo que se crea o modifica

## Convenciones de rutas

- Proyecto único Python: `src/` y `tests/` en la raíz del repositorio.
- Imports absolutos desde la raíz (`from src...`), sin imports relativos (`TID252`).
- Código, docstrings y documentación en español.

---

## Fase 1: Setup (infraestructura compartida)

**Propósito**: dejar lista la línea base, el paquete de salida y las puertas estáticas que usarán todas las fases.

- [ ] T001 Ejecutar la línea base de H001 con `uv run pytest tests/test_spec_001_triage.py -q` y confirmar que queda en verde antes de tocar la arquitectura.
- [ ] T002 Crear el paquete `src/adapters/outbound/__init__.py` para que `python -m src.adapters.outbound.sqlite_repository` resuelva desde la raíz.
- [ ] T003 [P] Configurar Ruff en `pyproject.toml`: `[tool.ruff]` con `target-version = "py310"` y `[tool.ruff.lint]` con `select = ["E4", "E7", "E9", "F", "TID"]`.
- [ ] T004 [P] Crear `src/domain/ruff.toml` con `extend = "../../pyproject.toml"`, `TID252` activo y `TID251` prohibiendo `src.application`, `src.adapters`, `src.composition`, `src.models`, `src.sla_calculator`, `src.incident_repository`, `fastapi`, `typer` y `sqlite3`.
- [ ] T005 [P] Crear `src/application/ruff.toml` con `extend = "../../pyproject.toml"` y `TID251` prohibiendo `src.adapters`, `src.composition`, `src.models`, `src.sla_calculator`, `src.incident_repository`, `fastapi`, `typer` y `sqlite3`.
- [ ] T006 [P] Crear `src/adapters/inbound/ruff.toml` con `extend = "../../pyproject.toml"` y `TID251` prohibiendo `src.adapters.outbound.sqlite_repository`, el legado (`src.composition`, `src.models`, `src.sla_calculator`, `src.incident_repository`) y `src.adapters.inbound.api` desde el CLI.

**Punto de control**: la suite de H001 pasa y `uv run ruff check src/` puede ejecutarse con la configuración raíz.

---

## Fase 2: Foundational (prerrequisitos bloqueantes)

**Propósito**: dominio migrado, puerto explícito, persistencia SQLite optimizada, fábrica, caso de uso y contrato de transporte. Ninguna historia puede empezar hasta completar esta fase.

**⚠️ CRÍTICO**: las tareas T007–T023 bloquean las tres historias.

- [ ] T007 [P] Crear `src/domain/models.py` con `IncidentStatus` (`Literal` con `OPEN`, `IN_PROGRESS`, `RESOLVED`, `CLOSED`), `Incident`, `SLARule`, `SLAEvaluation`, `ActiveIncidentDetail` y `ActiveIncidentsSummary` como `dataclass(frozen=True)`. Aplicar las reglas de `data-model.md` para `Incident.incident_id` (no vacío), `Incident.title` (texto sin truncar), `Incident.component` (no vacío), `Incident.severity`, `Incident.status`, `Incident.created_at` (naive), `Incident.resolved_at` (naive, obligatorio en terminales), `Incident.raw_text`, `SLARule.severity`, `SLARule.max_resolution_minutes`, `SLARule.operates_24x7`, `SLARule.escalation_threshold_ratio`, `SLAEvaluation.incident_id`, `SLAEvaluation.severity`, `SLAEvaluation.elapsed_minutes`, `SLAEvaluation.allowed_minutes`, `SLAEvaluation.remaining_minutes`, `SLAEvaluation.is_breached`, `SLAEvaluation.requires_escalation`, `ActiveIncidentDetail.incident`, `ActiveIncidentDetail.evaluation`, `ActiveIncidentsSummary.total_active`, `ActiveIncidentsSummary.breached_count` y `ActiveIncidentsSummary.incidents`.
- [ ] T008 Implementar en `src/domain/sla_calculator.py` la política `SLA_POLICY_TABLE` como `MappingProxyType`, `get_sla_rule_for_severity` y `evaluate_sla_status`, respetando `data-model.md` para `SLARule.max_resolution_minutes`, `SLARule.operates_24x7`, `SLARule.escalation_threshold_ratio`, `SLAEvaluation.elapsed_minutes`, `SLAEvaluation.allowed_minutes`, `SLAEvaluation.remaining_minutes`, `SLAEvaluation.is_breached` y `SLAEvaluation.requires_escalation`; el escalamiento exige estado activo y el incumplimiento es estrictamente `elapsed > allowed`.
- [ ] T009 Implementar en `src/domain/sla_calculator.py` `summarize_active_incidents(incidents, reference_time)` y la excepción de dominio para `created_at > reference_time`; el orden y los totales deben cumplir los invariantes de `data-model.md` §1 para `ActiveIncidentsSummary.total_active`, `ActiveIncidentsSummary.breached_count`, `ActiveIncidentsSummary.incidents`, `ActiveIncidentDetail.incident` y `ActiveIncidentDetail.evaluation`. Esta tarea no añade reglas nuevas: solo materializa las ya fijadas en el modelo.
- [ ] T010 [P] Crear `tests/domain/test_sla_calculator.py` con pruebas table-driven de `data-model.md` §6: P0 en 44/45/46 min, P2 en 359/360/361 y 479/480/481 min, fin de semana viernes 17:00 → lunes 09:00, escalamiento exacto al 75 %, escalamiento desactivado al incumplir, exclusión de terminales y aborto por incoherencia temporal. Debe fallar antes de T008/T009.
- [ ] T011 [P] Declarar `src/application/ports.py` con `IncidentRepositoryPort` como `Protocol` `@runtime_checkable` y los cinco métodos del contrato de `data-model.md` §4: `save_incident`, `get_incident`, `find_open_duplicates`, `list_active_incidents` y `check_health`, con firmas y tipos de retorno exactos.
- [ ] T012 Crear en `src/adapters/outbound/sqlite_repository.py` la conexión SQLite con `check_same_thread=False` y cerrojo, el DDL de `data-model.md` §3, el índice `idx_incidents_component_status (component, status)`, la siembra idempotente de `SLA_POLICY_TABLE` y la migración de `Incident.raw_text` mediante `PRAGMA table_info` + `ALTER TABLE`.
- [ ] T013 Completar en `src/adapters/outbound/sqlite_repository.py` `save_incident`, `get_incident`, `find_open_duplicates` y `check_health`, con el mapeo fila → entidad de `data-model.md` §3: validar `Incident.severity` contra la política, convertir `Incident.created_at` y `Incident.resolved_at` con `datetime.fromisoformat` y rechazar fechas con zona horaria.
- [ ] T014 Implementar en `src/adapters/outbound/sqlite_repository.py` `list_active_incidents(component_filter)` con una sola sentencia `SELECT` de columnas explícitas, `INNER JOIN sla_policies` y filtro de estado activo en SQL, conforme al contrato de `data-model.md` §4 y sin calcular SLA ni ordenar en el adaptador.
- [ ] T015 Añadir a `src/adapters/outbound/sqlite_repository.py` el bloque `if __name__ == "__main__"` con `--records` y `--iterations`, siembra sintética de 10.000 incidentes, resumen filtrado por componente y salida del `EXPLAIN QUERY PLAN`.
- [ ] T016 Crear `src/adapters/outbound/factory.py` con `create_repository(database_url: Optional[str] = None)` y `build_incident_service(...)`, resolución de `DATABASE_URL` según `data-model.md` §5 (ausente o `sqlite:///:memory:` → memoria; `sqlite:///ruta` → archivo; otro esquema → error de configuración claro).
- [ ] T017 Modificar `src/application/services.py`: inyectar `IncidentRepositoryPort` en `IncidentService`, añadir `DataInconsistencyError` y `get_active_incidents_summary(reference_time: Optional[datetime] = None)`, que llama a `list_active_incidents`, delega el cálculo en `summarize_active_incidents` y traduce la incoherencia temporal a un error con código `SUMMARY_REFERENCIA_INCONSISTENTE`.
- [ ] T018 [P] Crear `src/adapters/inbound/summary_contract.py` con los modelos Pydantic v2 `ActiveIncidentItem` y `ActiveIncidentsSummaryResponse`, la función `to_summary_response(summary)` y el analizador compartido `parse_reference_time`, respetando `contracts/summary.schema.json` y mapeando `ActiveIncidentsSummary.total_active`, `ActiveIncidentsSummary.breached_count`, `ActiveIncidentsSummary.incidents`, `SLAEvaluation.elapsed_minutes`, `SLAEvaluation.is_breached` y `SLAEvaluation.requires_escalation`.
- [ ] T019 [P] Añadir a `src/adapters/inbound/problem.py` los títulos de `SUMMARY_COMPONENTE_DEMASIADO_LARGO`, `SUMMARY_REFERENCIA_INVALIDA`, `SUMMARY_SOLICITUD_INVALIDA`, `SUMMARY_REFERENCIA_INCONSISTENTE` y `SUMMARY_ERROR_INTERNO`, sin alterar los códigos `TRIAGE_*` existentes.
- [ ] T020 Modificar `src/adapters/inbound/api/errors.py` para elegir el prefijo `SUMMARY_*` o `TRIAGE_*` según la ruta, traducir `DataInconsistencyError` a `409` y los fallos inesperados a `500` sin exponer detalles internos.
- [ ] T021 Reemplazar el uso de `src.composition` por `src.adapters.outbound.factory` en `src/adapters/inbound/cli.py`, `src/adapters/inbound/api/app.py`, `tests/conftest.py` y `tests/application/test_services.py`; los tests de triaje deben seguir en verde con el repositorio inyectado.
- [ ] T022 Retirar `src/models.py`, `src/sla_calculator.py`, `src/incident_repository.py` y `src/composition.py`, y verificar que no queda ningún import a esos módulos; no se modifica `legacy/triage_rules.py`, que permanece congelado y sin importar.
- [ ] T023 [P] Crear `tests/adapters/test_sqlite_repository.py` con la verificación estructural de `IncidentRepositoryPort` mediante `inspect.signature`, el conteo de una sola consulta por resumen, el plan de consulta con `idx_incidents_component_status`, la migración de `raw_text` y el rechazo de `DATABASE_URL` con esquema no soportado.

**Punto de control**: `uv run pytest` y `uv run ruff check src/` pasan; el dominio, el puerto, el adaptador SQLite y la fábrica están listos para las historias.

---

## Fase 3: Historia de Usuario 1 - Consultar el resumen por HTTP (Prioridad: P1) 🎯 MVP

**Objetivo**: entregar el resumen completo (total activo, total incumplido y detalle ordenado) por `GET /api/v1/incidents/summary`, sin filtro por componente.

**Prueba independiente**: sobre una base sembrada con activos y terminales, una única petición HTTP devuelve los totales correctos y una entrada por activo, sin terminales y sin valores parciales.

### Pruebas de la Historia 1

- [ ] T024 [US1] Crear `tests/test_spec_002_summary.py` con los escenarios Dado/Cuando/Entonces de US1: 5 activos y 3 terminales, 2 incumplidos de 4, detalle completo por incidente y resumen vacío. Usar una base SQLite temporal sembrada y un `reference_time` fijo; deben fallar antes de T026.
- [ ] T025 [US1] Añadir a `tests/test_spec_002_summary.py` los escenarios de error de US1: `reference_time` con zona o mal formado → `422 SUMMARY_REFERENCIA_INVALIDA`, incidente activo creado después del instante → `409 SUMMARY_REFERENCIA_INCONSISTENTE` sin totales, y terminal con SLA vencido excluido del resumen.

### Implementación de la Historia 1

- [ ] T026 [US1] Implementar `GET /api/v1/incidents/summary` en `src/adapters/inbound/api/app.py` con `reference_time` opcional, llamada a `get_active_incidents_summary`, mapeo mediante `to_summary_response` y `response_model=ActiveIncidentsSummaryResponse`.
- [ ] T027 [US1] Registrar en `src/adapters/inbound/api/app.py` los manejadores de `DataInconsistencyError` y de error inesperado definidos en `src/adapters/inbound/api/errors.py`, y asegurar que un `reference_time` inválido responde `422` con `SUMMARY_REFERENCIA_INVALIDA` y sin cuerpo de resumen.

**Punto de control**: US1 funciona de forma independiente con `uv run pytest tests/test_spec_002_summary.py -k "http or resumen"` y con la sección 3 de `quickstart.md`.

---

## Fase 4: Historia de Usuario 2 - Obtener el mismo resumen por consola (Prioridad: P1)

**Objetivo**: exponer el mismo caso de uso como `summary` en la CLI, con JSON idéntico al HTTP y códigos de salida estables.

**Prueba independiente**: con la misma base y el mismo `reference_time`, el documento JSON de la CLI es estrictamente igual al de HTTP; un error de entrada sale con código distinto de cero y `stdout` vacío.

### Pruebas de la Historia 2

- [ ] T028 [US2] Añadir a `tests/test_spec_002_summary.py` la prueba de paridad HTTP/CLI: sembrar una base temporal, invocar `TestClient` y `CliRunner` con el mismo `reference_time`, parsear ambos JSON y comparar por igualdad estricta (SC-003); incluir el caso vacío con código `0`.
- [ ] T029 [US2] Añadir a `tests/test_spec_002_summary.py` las pruebas de error de la CLI: fecha mal formada o con zona → código `2` y `SUMMARY_REFERENCIA_INVALIDA` en `stderr`, e incoherencia temporal → código `1` sin resumen parcial en `stdout`.

### Implementación de la Historia 2

- [ ] T030 [US2] Implementar el subcomando `summary` en `src/adapters/inbound/cli.py` con `--reference-time`, salida JSON por `stdout` mediante `summary_contract` y construcción del servicio con `src.adapters.outbound.factory`.
- [ ] T031 [US2] Implementar en `src/adapters/inbound/cli.py` la traducción de errores de la CLI: `SUMMARY_REFERENCIA_INVALIDA` y `SUMMARY_COMPONENTE_DEMASIADO_LARGO` → código `2` con problem+json en `stderr`; `SUMMARY_REFERENCIA_INCONSISTENTE` y fallos inesperados → código `1`, sin imprimir totales ni detalle.
- [ ] T032 [US2] Verificar que `src/adapters/inbound/cli.py` solo depende de `src.adapters.outbound.factory`, `src.application.services` y `summary_contract`, sin importar `src.adapters.inbound.api` ni `sqlite_repository`; ejecutar `uv run ruff check src/adapters/inbound/cli.py`.

**Punto de control**: US1 y US2 devuelven el mismo documento para los mismos datos e instante, y ambos canales traducen los mismos códigos de error.

---

## Fase 5: Historia de Usuario 3 - Filtrar el resumen por componente (Prioridad: P2)

**Objetivo**: limitar totales y detalle a un componente, con espacios exteriores ignorados, filtro vacío equivalente a "todos" y resultado vacío exitoso cuando no hay coincidencias.

**Prueba independiente**: con activos en `payments-gateway` y `auth-identity`, una consulta filtrada por uno de ellos devuelve solo ese subconjunto y totales coherentes, tanto por HTTP como por CLI.

### Pruebas de la Historia 3

- [ ] T033 [US3] Añadir a `tests/test_spec_002_summary.py` los escenarios de filtro en ambos canales: subconjunto por componente, componente sin coincidencias con `200`/código `0` y totales en cero, espacios sobrantes ignorados y filtro ausente o vacío equivalente a todos.
- [ ] T034 [US3] Añadir a `tests/adapters/test_sqlite_repository.py` la comprobación de que la consulta filtrada por componente usa `idx_incidents_component_status` y sigue emitiendo una sola sentencia SQL.

### Implementación de la Historia 3

- [ ] T035 [US3] Ampliar `get_active_incidents_summary` en `src/application/services.py` con `component_filter: Optional[str] = None`: recortar espacios, convertir vacío en `None`, rechazar más de 128 caracteres con `SUMMARY_COMPONENTE_DEMASIADO_LARGO` y pasar el filtro a `list_active_incidents`, conforme a `contracts/summary-api.md` y al contrato de `data-model.md` §4.
- [ ] T036 [US3] Añadir el parámetro de consulta `component` a `GET /api/v1/incidents/summary` en `src/adapters/inbound/api/app.py` y pasarlo al caso de uso, manteniendo `422 SUMMARY_COMPONENTE_DEMASIADO_LARGO` para valores fuera de límite.
- [ ] T037 [US3] Añadir la opción `--component` al subcomando `summary` en `src/adapters/inbound/cli.py`, pasarla al caso de uso y conservar la paridad JSON con HTTP.

**Punto de control**: las tres historias funcionan de forma independiente y la filtrada mantiene la paridad y el orden definidos en el dominio.

---

## Fase 6: Polish y preocupaciones transversales

**Propósito**: cerrar la gobernanza documental, la verificación estática y la evidencia de rendimiento exigidas por `plan.md`.

- [ ] T038 [P] Crear `docs/adr/005-resumen-activos-hexagonal.md` con el contexto, la decisión, las alternativas, la topología `inbound → application → domain` y `outbound → application`, el puerto único y la fábrica como raíz de composición, incluyendo un diagrama Mermaid.
- [ ] T039 [P] Aplicar la enmienda PATCH a `docs/constitution.md` y `.specify/memory/constitution.md` para nombrar `src/adapters/outbound/factory.py` como raíz de composición y fijar el conjunto de puertos vigente en H002 (`IncidentRepositoryPort`).
- [ ] T040 [P] Actualizar `docs/adr/002-calculo-sla-horario-habil.md` para reflejar la migración del cálculo a `src/domain/sla_calculator.py`, la inmutabilidad de `SLA_POLICY_TABLE` y el escalamiento solo en estados activos.
- [ ] T041 [P] Actualizar `README.md` con el nuevo comando `summary`, la ruta HTTP, `DATABASE_URL` y el retiro de `python -m src.sla_calculator` y `python -m src.incident_repository`.
- [ ] T042 [P] Actualizar `AGENTS.md` para retirar los comandos del legado, documentar `summary`, la fábrica como raíz de composición y las rutas nuevas del dominio.
- [ ] T043 [P] Actualizar `docs/ROADMAP.md` para marcar H002 como entregado y registrar la deuda pendiente de H003 (similitud y ventana de duplicados).
- [ ] T044 Ejecutar `uv run pytest -v` y corregir los fallos en `src/` y `tests/` sin desactivar pruebas ni usar `# noqa`.
- [ ] T045 Ejecutar `uv run ruff check src/` y corregir todos los hallazgos en `src/` sin `# noqa`, sin desactivar reglas y sin imports relativos.
- [ ] T046 Ejecutar `uv run python -m src.adapters.outbound.sqlite_repository --records 10000 --iterations 20` y anexar a `docs/adr/005-resumen-activos-hexagonal.md` la evidencia de SC-001, el conteo de consultas y el uso de `idx_incidents_component_status`.
- [ ] T047 Recorrer `specs/001-active-incidents-summary/quickstart.md` de la sección 1 a la 7 y corregir en `src/` cualquier desviación de comandos, códigos o salidas; dejar constancia en `docs/adr/005-resumen-activos-hexagonal.md` si alguna comprobación cambia de forma.

---

## Dependencias y orden de ejecución

### Dependencias por fase

- **Setup (Fase 1)**: sin dependencias; T003–T006 pueden ir en paralelo.
- **Foundational (Fase 2)**: depende de Setup; T007–T023 bloquean las tres historias.
- **Historias (Fases 3–5)**: dependen de Foundational.
  - US1 y US2 pueden ejecutarse en paralelo entre sí una vez completada la Fase 2, porque tocan archivos distintos (`api/app.py` frente a `cli.py`) y comparten el contrato ya creado.
  - US3 depende de US1 y US2 porque modifica ambos adaptadores y el caso de uso compartido.
- **Polish (Fase 6)**: depende de que las historias elegidas estén completas.

### Dependencias entre historias

- **US1 (P1)**: empieza tras Foundational; no depende de US2 ni US3.
- **US2 (P1)**: empieza tras Foundational; comparte servicio y contrato con US1, pero se valida de forma independiente.
- **US3 (P2)**: empieza tras US1 y US2 porque añade el filtro a los dos canales y al caso de uso.

### Dentro de cada historia

1. Las pruebas se escriben y fallan antes de la implementación (T024–T025, T028–T029, T033–T034).
2. El caso de uso se amplía antes de los adaptadores (T035 antes de T036–T037).
3. La implementación del adaptador precede a la verificación de paridad y de fronteras.

---

## Ejemplos de ejecución paralela

### Setup

```text
Tarea: Configurar Ruff en pyproject.toml
Tarea: Crear src/domain/ruff.toml
Tarea: Crear src/application/ruff.toml
Tarea: Crear src/adapters/inbound/ruff.toml
```

### Foundational

```text
Tarea: Crear src/domain/models.py
Tarea: Declarar src/application/ports.py
Tarea: Crear src/adapters/inbound/summary_contract.py
Tarea: Añadir títulos SUMMARY_* en src/adapters/inbound/problem.py
Tarea: Crear tests/adapters/test_sqlite_repository.py
```

### Historias US1 y US2 en paralelo

```text
Desarrollador A: T024–T027 (HTTP: tests/test_spec_002_summary.py y src/adapters/inbound/api/app.py)
Desarrollador B: T028–T032 (CLI: tests/test_spec_002_summary.py y src/adapters/inbound/cli.py)
```

> US1 y US2 comparten `tests/test_spec_002_summary.py`; si se ejecutan en paralelo, cada desarrollador debe coordinar el bloque de pruebas que añade para evitar conflictos de edición.

### Polish documental

```text
Tarea: ADR-005 en docs/adr/005-resumen-activos-hexagonal.md
Tarea: Enmienda en docs/constitution.md y .specify/memory/constitution.md
Tarea: Actualización de README.md
Tarea: Actualización de AGENTS.md
Tarea: Actualización de docs/ROADMAP.md
```

---

## Estrategia de implementación

### MVP primero (US1)

1. Completar Fase 1 (Setup).
2. Completar Fase 2 (Foundational): es bloqueante para todo.
3. Completar Fase 3 (US1).
4. **PARAR y VALIDAR**: ejecutar T024–T025 y la sección 3 de `quickstart.md`.
5. Desplegar o demostrar el resumen HTTP si el alcance lo permite.

El MVP entrega el valor central: totales y detalle por HTTP. US2 es igualmente P1 y completa el requisito de paridad entre canales; H002 no se cierra sin ella.

### Entrega incremental

1. Setup + Foundational → base hexagonal y persistencia optimizada.
2. US1 → resumen HTTP verificable de forma independiente (MVP).
3. US2 → paridad CLI/HTTP y cierre de la semántica de dos canales.
4. US3 → filtro por componente sin romper las historias anteriores.
5. Polish → ADR-005, enmienda de la Constitución, documentación y evidencia de rendimiento.

### Estrategia con varios desarrolladores

1. El equipo completa Setup y Foundational en conjunto.
2. Tras Foundational:
   - Desarrollador A: US1 (HTTP).
   - Desarrollador B: US2 (CLI).
3. Al integrarse US1 y US2, un desarrollador toma US3 y otro la documentación de Polish.
4. Las historias se integran de forma independiente y cada una conserva su prueba de aceptación.

---

## Notas

- `[P]` indica archivos distintos y ausencia de dependencia con tareas incompletas.
- `[US1]`, `[US2]` y `[US3]` permiten rastrear cada tarea hasta su historia y su criterio de aceptación.
- No se debe reintroducir lógica de SLA, orden ni totales en `src/application/` ni en `src/adapters/`; el dominio es la única fuente.
- No se debe reactivar la deuda `SELECT *`/N+1: H002 es su refactor y la consulta debe seguir siendo una sola sentencia.
- `legacy/triage_rules.py` permanece congelado: no se importa, no se modifica y no se usa como fuente de verdad.
- Cada tarea o grupo lógico debe terminar con `uv run pytest` en verde y `uv run ruff check src/` sin hallazgos antes de pasar a la siguiente.
