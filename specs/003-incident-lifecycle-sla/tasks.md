---

description: "Lista de tareas ejecutables para el ciclo de vida, duplicados y SLA (H003)"
---

# Tareas: Ciclo de vida, duplicados y SLA (H003)

**Entrada**: Documentos de diseño en `/specs/003-incident-lifecycle-sla/`

**Prerrequisitos**: [plan.md](./plan.md) y [spec.md](./spec.md) (obligatorios);
[research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/) y
[quickstart.md](./quickstart.md).

**Pruebas**: la Constitución §VII y los criterios de cierre del plan exigen escenarios BDD
ejecutables, por lo que las tareas de prueba son obligatorias en este hito. Se escriben antes de la
implementación de cada historia y deben fallar primero.

**Organización**: las tareas se agrupan por historia de usuario para que cada incremento sea
implementable y verificable por separado. Las citas `data-model.md` → `Entidad.campo` identifican la
definición canónica de cada campo restringido; no se duplican aquí sus reglas.

## Formato: `[ID] [P?] [Story] Descripción`

- **[P]**: puede ejecutarse en paralelo (archivos distintos, sin dependencias pendientes).
- **[Story]**: historia de usuario a la que pertenece la tarea (`US1`…`US4`).
- Todas las rutas son relativas a la raíz del repositorio.

## Convenciones de rutas

- Dominio: `src/domain/`
- Aplicación: `src/application/`
- Adaptadores: `src/adapters/inbound/` y `src/adapters/outbound/`
- Pruebas: `tests/` (aceptación en la raíz, unitarias por capa)
- Gobernanza: `docs/adr/`, `AGENTS.md`, `README.md`, `docs/ROADMAP.md`

---

## Fase 1: Setup (infraestructura compartida)

**Propósito**: partir de una base verde y de la rama correcta, sin tocar el stack.

- [ ] T001 Recrear la rama actual desde `main` (la rama actual está por detrás y no contiene H002) y validar la línea base con `uv sync`, `uv run pytest -v` y `uv run ruff check src/`, usando `pyproject.toml` y `uv.lock` como referencia del stack.
- [ ] T002 [P] Confirmar que H003 no añade dependencias ni relaja fronteras: verificar `[tool.uv] package = false`, `target-version = "py310"`, `select = ["E4", "E7", "E9", "F", "TID"]` en `pyproject.toml` y los `ruff.toml` de `src/domain/`, `src/application/`, `src/adapters/inbound/` y `src/adapters/inbound/api/`, sin modificar `uv.lock`.

---

## Fase 2: Foundational (prerrequisitos bloqueantes)

**Propósito**: tipos de dominio, errores de aplicación, contrato de transporte y persistencia que
necesitan las cuatro historias. Ninguna historia puede cerrarse sin esta fase.

**⚠️ CRÍTICO**: completar T003–T010 antes de empezar cualquier historia de usuario.

- [ ] T003 [P] Extender `src/domain/models.py`: añadir `Incident.recommended_team: Optional[Team] = None` e `Incident.duplicate_group_key: Optional[str] = None` al final del `dataclass`, y declarar `SLAComputationWindow` y `SLAEvaluationDetail` como `frozen=True`, exportándolos en `__all__`. Citas: `data-model.md` → `Incident.recommended_team`, `Incident.duplicate_group_key`, `SLAComputationWindow`, `SLAEvaluationDetail.incident`, `SLAEvaluationDetail.evaluation`, `SLAEvaluationDetail.reference_time`, `SLAEvaluationDetail.window`.
- [ ] T004 [P] Centralizar la normalización temporal y la evaluación con contexto en `src/domain/sla_calculator.py`: `validar_instante_naive(instante, campo)`, `resolver_ventana_temporal(incident, reference_time)` y `evaluate_sla_detail(incident, reference_time) -> SLAEvaluationDetail`, conservando intactas la firma y la aritmética de `evaluate_sla_status`. Citas: `data-model.md` → `Incident.created_at`, `Incident.resolved_at`, `Incident.status`, `SLAEvaluationDetail.window`, `SLAEvaluationDetail.reference_time`.
- [ ] T005 [P] Añadir las reglas de equivalencia en `src/domain/triage_rules.py`: `DUPLICATE_SIMILARITY_THRESHOLD = 0.75`, `DUPLICATE_WINDOW_DAYS` (P0 1, P1 2, P2 3, P3 4), `DuplicateAssessment` con la propiedad `is_duplicate`, `is_equivalent(older, newer)` y `assess_duplicates(new_incident, candidates)` según el algoritmo del modelo de datos. Citas: `data-model.md` → `DuplicateAssessment.duplicate_group_key`, `DuplicateAssessment.duplicate_of`, `DuplicateAssessment.is_duplicate`, `Incident.raw_text`.
- [ ] T006 [P] Ampliar `src/application/services.py`: `DataInconsistencyError` con `status: int = 409`, `IncidentAlreadyExistsError`, `IncidentNotFoundError`, `IncidentCreationResult`, las constantes de código `CREATE_*` y `SLA_*`, y un parámetro opcional `now: Optional[Callable[[], datetime]]` en `IncidentService.__init__` con `datetime.now` por defecto. Citas: `data-model.md` → `IncidentCreationResult.incident`, `IncidentCreationResult.duplicate`.
- [ ] T007 [P] Ampliar el esquema y el mapeo en `src/adapters/outbound/sqlite_repository.py`: columnas `recommended_team TEXT` y `duplicate_group_key TEXT`, migración idempotente con `PRAGMA table_info` + `ALTER TABLE`, índice `idx_incidents_dup_key (duplicate_group_key, status)`, escritura con `INSERT` estricto que traduce `sqlite3.IntegrityError` a `IncidentAlreadyExistsError`, y siembra sintética con sentencia propia e idempotente. Citas: `data-model.md` → `Incident.recommended_team`, `Incident.duplicate_group_key`.
- [ ] T008 [P] Crear `src/adapters/inbound/temporal_contract.py` con `PATRON_INSTANTE` y `parse_instante_naive(valor, campo, codigo)`, y hacer que `parse_reference_time` de `src/adapters/inbound/summary_contract.py` delegue en él conservando `SUMMARY_REFERENCIA_INVALIDA` y su comportamiento actual.
- [ ] T009 [P] Crear `src/adapters/inbound/lifecycle_contract.py` con `CreateIncidentRequest`, `IncidentCreatedResponse`, `SLAEvaluationResponse` (todos con `extra="forbid"`), `derivar_titulo(raw_text)` determinista, y las funciones de mapeo desde el dominio. Citas: `data-model.md` → `Incident.incident_id`, `Incident.title`, `DuplicateAssessment.duplicate_of`, `DuplicateAssessment.is_duplicate`.
- [ ] T010 [P] Elegir el prefijo de error por ruta en `src/adapters/inbound/api/errors.py` (`/incidents/triage` → `TRIAGE`, `/summary` → `SUMMARY`, `/incidents` → `CREATE`, `/incidents/{id}/sla` → `SLA`, evaluando `/summary` antes del patrón con identificador), añadir los títulos de `CREATE_*` y `SLA_*` en `src/adapters/inbound/problem.py`, hacer que el manejador de `DataInconsistencyError` use `exc.status`, y registrar en `src/adapters/inbound/api/app.py` los manejadores de `IncidentNotFoundError` (404) e `IncidentAlreadyExistsError` (409).

**Punto de control**: dominio, puerto, persistencia y contrato de transporte listos; las historias pueden
comenzar.

---

## Fase 3: Historia de Usuario 1 · Alta persistente de incidentes (Prioridad: P1) 🎯 MVP

**Objetivo**: registrar un reporte por HTTP y CLI, clasificarlo con el triaje canónico, persistirlo en
estado `OPEN` y recuperarlo tras reiniciar el proceso, rechazando conflictos de identificador y
entradas inválidas sin persistir nada.

**Prueba independiente**: registrar un reporte válido por cualquiera de los dos canales, reiniciar el
proceso sobre el mismo archivo SQLite y verificar que `get_incident`, el resumen de activos y `sla`
devuelven el mismo identificador, título, componente, severidad, estado y texto original; repetir el
identificador produce `409`/salida `1` y una entrada vacía produce `422`/salida `2`.

### Pruebas de la Historia 1 (escribir primero, deben fallar)

- [ ] T011 [P] [US1] Escribir los escenarios BDD del alta persistente en `tests/test_spec_003_lifecycle_sla.py`: `201` con clasificación y `OPEN`, recuperación tras recrear el repositorio sobre el mismo archivo, aparición en `summary`, `409 CREATE_ID_CONFLICTO` sin sobrescritura y `422`/salida `2` para identificador o texto vacíos, sólo espacios o demasiado largos.
- [ ] T012 [P] [US1] Añadir pruebas del caso de uso de alta en `tests/application/test_services.py` con un doble de `IncidentRepositoryPort`: resolución única de `now`, título derivado, propagación de conflicto y códigos `CREATE_*` de validación.
- [ ] T013 [P] [US1] Añadir pruebas del adaptador en `tests/adapters/test_sqlite_repository.py`: ida y vuelta de `recommended_team` y `duplicate_group_key`, migración de una base sin las columnas nuevas, conflicto de `save_incident` sin sobrescritura y siembra idempotente.

### Implementación de la Historia 1

- [ ] T014 [US1] Implementar `IncidentService.create_incident` en `src/application/services.py`: validar y recortar identificador y texto, derivar u validar el título, resolver `now` una sola vez si falta `created_at`, clasificar con `classify_impact`, construir el `Incident` en `OPEN` con `duplicate_group_key=None`, persistir y devolver `IncidentCreationResult` con `DuplicateAssessment(None, ())`; traducir el conflicto del puerto a `IncidentAlreadyExistsError`. Citas: `data-model.md` → `Incident.incident_id`, `Incident.title`, `Incident.component`, `Incident.severity`, `Incident.status`, `Incident.created_at`, `Incident.raw_text`.
- [ ] T015 [P] [US1] Registrar `POST /api/v1/incidents` en `src/adapters/inbound/api/app.py` con `CreateIncidentRequest`/`IncidentCreatedResponse` como modelos y `status_code=201`, sin lógica de negocio en la ruta.
- [ ] T016 [P] [US1] Añadir el subcomando `create` en `src/adapters/inbound/cli.py` con `--incident-id`, `--raw-text`/`--raw-text -`, `--file`, `--title` y `--created-at`, validando exclusividad de fuentes y coherencia con `--file`; imprimir el documento con `model_dump(mode="json")` y salir con `0`, `1` o `2` según el contrato.
- [ ] T017 [P] [US1] Completar en `src/adapters/inbound/api/errors.py` la traducción del conflicto de alta a `409 CREATE_ID_CONFLICTO`, usando el manejador ya registrado en T010, y verificar que no se emite documento parcial ni se escribe nada (la CLI mapea el mismo error a salida `1` en T016).

**Punto de control**: el alta persistente funciona por HTTP y CLI y se recupera tras reiniciar el
proceso. Es el MVP del hito.

---

## Fase 4: Historia de Usuario 2 · Aviso de duplicados abiertos (Prioridad: P1)

**Objetivo**: devolver en la misma respuesta `201` si existen incidentes equivalentes previos, con
`duplicate_of` ordenado y `duplicate_group_key` heredada del original, sin fusionar ni modificar
incidentes existentes y serializando por componente las altas concurrentes.

**Prueba independiente**: con un original activo almacenado, un reporte equivalente del mismo
componente y dentro de la ventana de la severidad del más antiguo devuelve `is_duplicate=true` y el
identificador del original; los casos de candidato terminal, otro componente, similitud por debajo del
umbral, fuera de ventana, sin `raw_text` o posterior al nuevo devuelven `false`; dos altas concurrentes
del mismo componente quedan ambas persistidas y la segunda avisa a la primera.

### Pruebas de la Historia 2 (escribir primero, deben fallar)

- [ ] T018 [P] [US2] Escribir el bloque BDD de duplicados en `tests/test_spec_003_lifecycle_sla.py`: aviso simple, ausencia de falsos positivos, grupo heredado, original más antiguo sin clave, orden de `duplicate_of` y aviso sin fusión ni modificación de los previos.
- [ ] T019 [P] [US2] Crear `tests/domain/test_duplicate_rules.py` con casos table-driven: similitud `0.74`/`0.75`, frontera exacta de la ventana y un segundo por encima, ventana según la severidad del más antiguo, candidato terminal, otro componente, `raw_text` vacío, candidato posterior y herencia de la clave del original.
- [ ] T020 [US2] Añadir en `tests/test_spec_003_lifecycle_sla.py` la prueba de concurrencia con dos hilos y `threading.Barrier` sobre una base de archivo temporal, mismo componente y `created_at`/`incident_id` que hagan determinista que el segundo informe al primero.

### Implementación de la Historia 2

- [ ] T021 [US2] Conectar la detección al alta en `src/application/services.py`: dentro del cerrojo del componente, ejecutar `find_open_duplicates`, `assess_duplicates` y persistir el incidente con la `duplicate_group_key` resultante, devolviendo el mismo veredicto en `IncidentCreationResult`. Citas: `data-model.md` → `Incident.duplicate_group_key`, `DuplicateAssessment.duplicate_group_key`, `DuplicateAssessment.duplicate_of`, `DuplicateAssessment.is_duplicate`.
- [ ] T022 [US2] Añadir a `IncidentService` el registro de cerrojos por componente (guarda + `threading.Lock` por componente) que serializa detección y escritura dentro del proceso, sin puerto nuevo ni bloqueo distribuido, y documentar el límite en el docstring.

**Punto de control**: US1 y US2 funcionan juntas y los escenarios de falso positivo quedan cubiertos.

---

## Fase 5: Historia de Usuario 3 · Auditoría de SLA de un incidente (Prioridad: P1)

**Objetivo**: evaluar un incidente almacenado en un instante de referencia, congelar el cómputo en
`resolved_at` para terminales, informar la ventana aplicada y rechazar referencias anteriores a la
creación, identificadores inexistentes y datos incoherentes por HTTP y CLI.

**Prueba independiente**: un incidente `OPEN` evaluado en un instante explícito devuelve minutos
consumidos, permitidos, restantes, incumplimiento, escalamiento y ventana; las fronteras P0 60/61,
P1 180 y P2 viernes→lunes coinciden con la política; un terminal no crece con la referencia; una
referencia anterior a la creación devuelve `422`/salida `1`; un identificador inexistente devuelve
`404`/salida `1`; una fecha con zona devuelve `422`/salida `2`.

### Pruebas de la Historia 3 (escribir primero, deben fallar)

- [ ] T023 [P] [US3] Escribir el bloque BDD de SLA en `tests/test_spec_003_lifecycle_sla.py`: activo con contexto completo, fronteras P0 60/61 y P1 180, P2 viernes→lunes, terminal congelado antes y después de `resolved_at`, referencia anterior a la creación, identificador inexistente, referencia omitida y fecha aware.
- [ ] T024 [P] [US3] Ampliar `tests/domain/test_sla_calculator.py` con `validar_instante_naive`, `resolver_ventana_temporal` y `evaluate_sla_detail`: aware rechazado en los tres campos, `reference_time < created_at` rechazado también en terminales, `resolved_at` obligatorio en terminales y valores de `evaluate_sla_status` sin cambios.
- [ ] T025 [P] [US3] Añadir pruebas de `evaluate_incident_sla` en `tests/application/test_services.py`: `SLA_INCIDENTE_NO_ENCONTRADO`, `SLA_REFERENCIA_INCONSISTENTE`, `SLA_DATOS_INCONSISTENTES`, resolución única de `now` y operación de sólo lectura.
- [ ] T026 [P] [US3] Añadir pruebas de `get_incident` en `tests/adapters/test_sqlite_repository.py`: recupera activos y terminales, mapea `resolved_at`, `recommended_team` y `duplicate_group_key`, y rechaza severidad, estado o equipo fuera de catálogo y fechas aware.

### Implementación de la Historia 3

- [ ] T027 [US3] Implementar `IncidentService.evaluate_incident_sla` en `src/application/services.py`: resolver `now` una sola vez, cargar con `get_incident`, traducir ausencia a `IncidentNotFoundError`, delegar en `evaluate_sla_detail` y traducir `TemporalInconsistencyError`/`InvalidIncidentError` a `DataInconsistencyError` con `status=422` para la referencia incoherente o `409` para datos incoherentes; no escribir nada. Citas: `data-model.md` → `Incident.created_at`, `Incident.resolved_at`, `Incident.severity`, `Incident.status`, `SLAEvaluationDetail.window`.
- [ ] T028 [P] [US3] Registrar `GET /api/v1/incidents/{incident_id}/sla` en `src/adapters/inbound/api/app.py`, rechazar parámetros desconocidos o repetidos con `SLA_SOLICITUD_INVALIDA`, parsear `reference_time` con `temporal_contract` y responder con `SLAEvaluationResponse`.
- [ ] T029 [P] [US3] Añadir el subcomando `sla` en `src/adapters/inbound/cli.py` con `--incident-id` y `--reference-time`, serializando con `model_dump(mode="json")` y mapeando los fallos a salida `1` (inexistente o incoherente) y `2` (entrada inválida).
- [ ] T030 [P] [US3] Completar en `src/adapters/inbound/api/errors.py` el mapeo de `IncidentNotFoundError` a `404`, de `DataInconsistencyError` a `exc.status` (`409`/`422`) y de la referencia incoherente a `422 SLA_REFERENCIA_INCONSISTENTE`, sin documento parcial; los manejadores se registran en T010 y la ruta en T028.

**Punto de control**: las tres capacidades P1 funcionan de extremo a extremo por HTTP; el MVP completo
está disponible.

---

## Fase 6: Historia de Usuario 4 · Paridad de la consola con HTTP (Prioridad: P2)

**Objetivo**: garantizar que `create` y `sla` devuelven exactamente los mismos documentos, códigos y
valores que sus equivalentes HTTP, sin una segunda fuente de verdad.

**Prueba independiente**: para la misma entrada e instante, los documentos JSON de CLI y HTTP son
iguales campo por campo; los fallos equivalentes comparten `code` y la correspondencia
`422`/`404`/`409` → salida `2`/`1`/`1`, sin JSON parcial en `stdout`.

**Dependencia**: esta historia integra lo entregado por US1 y US3; no es independiente de ellas.

### Pruebas de la Historia 4 (escribir primero, deben fallar)

- [ ] T031 [P] [US4] Escribir el bloque BDD de paridad en `tests/test_spec_003_lifecycle_sla.py`: misma entrada de alta por HTTP y CLI comparada por igualdad estricta de documentos, mismo incidente/referencia de SLA comparado igual, y fallos equivalentes con el mismo `code` y distinto canal de salida.
- [ ] T032 [P] [US4] Ampliar `tests/adapters/test_cli.py` con `create` y `sla`: salida `0` con JSON, `--raw-text -` y `--file`, conflicto de `--incident-id` con el archivo, salidas `1` y `2`, y `stdout` vacío ante error.
- [ ] T033 [P] [US4] Ampliar `tests/adapters/test_api.py` con los contratos nuevos: `201` de alta, `200` de SLA, `403`/`404` ajenos al contrato, `422` por campo desconocido en cuerpo y por parámetro desconocido o repetido en consulta, y `content-type: application/problem+json`.

### Implementación de la Historia 4

- [ ] T034 [US4] Unificar la serialización de ambos canales: la CLI debe usar `model_dump(mode="json")` sobre los modelos de `src/adapters/inbound/lifecycle_contract.py` y ningún comando debe formatear fechas por su cuenta; ajustar `src/adapters/inbound/cli.py` y el contrato compartido si la prueba de paridad detecta divergencias, sin que la CLI importe `src.adapters.inbound.api`.

**Punto de control**: HTTP y consola son intercambiables para alta y SLA.

---

## Fase 7: Pulido y aspectos transversales

**Propósito**: gobernanza documental, evidencia de rendimiento y puertas de calidad del PR.

- [ ] T035 [P] Crear `docs/adr/006-ciclo-vida-duplicados-sla.md` con la plantilla `docs/adr/000-template.md`: detección en el dominio, `SLAEvaluationDetail`, cerrojos por componente, `INSERT` con conflicto, contrato compartido y un diagrama Mermaid de la topología.
- [ ] T036 [P] Actualizar `AGENTS.md` (comandos `create`/`sla`, códigos `CREATE_*`/`SLA_*` y retirada de la afirmación de que `duplicate_group_key` permanece `null`), `README.md` y `docs/ROADMAP.md` (H003 implementado), sin reescribir `CONTEXT_LOG.md` ni `SDD_LOG.md`.
- [ ] T037 [P] Revisar `docs/adr/002-calculo-sla-horario-habil.md` y anotar que H003 centraliza la validación temporal y congela el cómputo en `resolved_at` sin cambiar la aritmética de ventana hábil ni descontar festivos.
- [ ] T038 Extender la utilidad de plan de consulta de `src/adapters/outbound/sqlite_repository.py` para exponer `EXPLAIN QUERY PLAN` de la consulta por `duplicate_group_key`/`status`, y ejecutar `uv run python -m src.adapters.outbound.sqlite_repository --records 10000 --iterations 20` y `uv run python tools/benchmark_summary.py --records 10000 --iterations 20` para registrar el uso de `idx_incidents_dup_key` y los tiempos de alta/SLA como evidencia de SC-006.
- [ ] T039 Recorrer `specs/003-incident-lifecycle-sla/quickstart.md` de extremo a extremo sobre `sqlite:///ciclo-vida-demo.db` (alta, duplicado, conflicto, SLA 45/61, P2 viernes→lunes, reinicio, 404 y fecha aware) y corregir cualquier divergencia entre documento y comportamiento.
- [ ] T040 Ejecutar las puertas finales: `uv run ruff check src/` sin errores con `TID251`/`TID252`, `uv run pytest -v` completo con H001 y H002 sin cambios de valores, y verificar que no reaparecen `src/models.py` ni `src/sla_calculator.py`, que `legacy/triage_rules.py` sigue sin importarse y que `src/adapters/outbound/factory.py` sigue siendo la única raíz de composición.

---

## Dependencias y orden de ejecución

### Dependencias por fase

- **Setup (Fase 1)**: sin dependencias.
- **Foundational (Fase 2)**: depende de Setup y **bloquea** las cuatro historias.
- **US1 (Fase 3)**: depende de Foundational; no depende de otras historias.
- **US2 (Fase 4)**: depende de Foundational y de US1 (reutiliza `create_incident`); puede trabajarse en paralelo con US3 si hay capacidad, porque toca archivos distintos salvo `services.py`.
- **US3 (Fase 5)**: depende de Foundational; no depende de US1 en el dominio, pero su prueba de paridad y el escenario de reinicio usan incidentes creados por US1.
- **US4 (Fase 6)**: depende de US1 y US3 completas; integra ambos canales.
- **Pulido (Fase 7)**: depende de todas las historias deseadas.

### Dependencias dentro de cada historia

- Las pruebas se escriben y fallan antes de la implementación.
- Modelos y reglas de dominio antes que servicios; servicios antes que endpoints y comandos.
- `create_incident` (T014) antes de los bordes T015–T017.
- La detección (T021) antes de los cerrojos (T022), ambas sobre `src/application/services.py`.
- `evaluate_incident_sla` (T027) antes de los bordes T028–T030.

### Archivos compartidos que impiden paralelizar

- `src/application/services.py`: T006 → T014 → T021 → T022 → T027.
- `tests/test_spec_003_lifecycle_sla.py`: T011 → T018 → T020 → T023 → T031.
- `tests/application/test_services.py`: T012 → T025.
- `tests/adapters/test_sqlite_repository.py`: T013 → T026.
- `src/adapters/inbound/api/app.py`: T010 → T015 → T028.
- `src/adapters/inbound/api/errors.py`: T010 → T017 → T030.

---

## Oportunidades de paralelización

- **Fase 2**: T003 puede iniciar sola; después T004 y T005 en paralelo; T008 en paralelo con ellas; tras T006, ejecutar T007, T009 y T010 en paralelo (archivos distintos).
- **Fase 3**: T011, T012 y T013 en paralelo; tras T014, T015, T016 y T017 en paralelo.
- **Fase 4**: T018 y T019 en paralelo; T020 después de T018 por compartir `tests/test_spec_003_lifecycle_sla.py`; T021 y T022 secuenciales por compartir `services.py`.
- **Fase 5**: T023, T024, T025 y T026 en paralelo; tras T027, T028, T029 y T030 en paralelo.
- **Fase 6**: T031, T032 y T033 en paralelo; T034 después de que fallen o pasen.
- **Fase 7**: T035, T036 y T037 en paralelo; T038–T040 secuenciales.

### Ejemplo de ejecución paralela · US1

```text
Tarea: "Escenarios BDD de alta persistente en tests/test_spec_003_lifecycle_sla.py"
Tarea: "Pruebas del caso de uso de alta en tests/application/test_services.py"
Tarea: "Pruebas del adaptador en tests/adapters/test_sqlite_repository.py"
# Después de T014:
Tarea: "Endpoint POST /api/v1/incidents en src/adapters/inbound/api/app.py"
Tarea: "Subcomando create en src/adapters/inbound/cli.py"
Tarea: "Traducción de 409 CREATE_ID_CONFLICTO en src/adapters/inbound/api/errors.py"
```

### Ejemplo de ejecución paralela · US3

```text
Tarea: "Escenarios BDD de SLA en tests/test_spec_003_lifecycle_sla.py"
Tarea: "Pruebas de dominio de SLA en tests/domain/test_sla_calculator.py"
Tarea: "Pruebas de evaluate_incident_sla en tests/application/test_services.py"
Tarea: "Pruebas de get_incident en tests/adapters/test_sqlite_repository.py"
```

---

## Estrategia de implementación

### MVP primero (US1 + US2, ambas P1)

1. Completar Fase 1 y Fase 2.
2. Completar US1: alta persistente por HTTP y CLI.
3. **Parar y validar**: reinicio sobre el mismo archivo, conflicto y entradas inválidas.
4. Completar US2: aviso de duplicados en la misma respuesta y prueba de concurrencia.
5. **Parar y validar**: ausencia de falsos positivos y aviso sin fusión.

Las dos historias P1 de registro forman el primer incremento demostrable. US3 añade la segunda
capacidad P1 (SLA) y US4 cierra la paridad P2.

### Entrega incremental

1. Fases 1–2 → base compartida.
2. US1 → alta persistente verificable.
3. US2 → aviso de duplicados verificable.
4. US3 → auditoría de SLA verificable.
5. US4 → paridad estricta HTTP/CLI.
6. Fase 7 → ADR, documentación y evidencia de rendimiento.

---

## Notas

- `[P]` indica archivos distintos y dependencias previas ya completas; no autoriza a dos tareas a
  editar el mismo archivo a la vez.
- Cada tarea debe dejar la suite en verde o, en las tareas de prueba, en rojo esperado antes de su
  implementación.
- No se crean `src/models.py` ni `src/sla_calculator.py`; las reglas viven solo en `src/domain/`.
- La CLI no importa `src.adapters.inbound.api`; comparte `lifecycle_contract.py` y `temporal_contract.py`.
- `CONTEXT_LOG.md` y `SDD_LOG.md` no se reescriben.
- Los festivos siguen siendo deuda documentada (ADR-002).
