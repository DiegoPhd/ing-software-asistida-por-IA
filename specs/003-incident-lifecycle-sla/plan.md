# Plan de Implementación: Ciclo de vida, duplicados y SLA (H003)

**Rama de trabajo**: rama actual · **Rama de entrega**: rama actual

**Fecha**: 2026-11-22 | **Spec**: [spec.md](./spec.md)

**Entrada**: Especificación `specs/003-incident-lifecycle-sla/spec.md` y descripción del Hito 003
(alta persistente, aviso de duplicados abiertos y auditoría de SLA por HTTP y consola).

> Nota de rama: `setup-plan.ps1` informó `003-incident-lifecycle-sla`, que no existe en el
> repositorio. La rama actual existe pero está **por detrás de `main`** (no
> contiene H002). Debe recrearse desde `main` antes de implementar; el trabajo no se ramifica
> desde el estado actual de `reto-3`.

## Resumen

H003 añade dos casos de uso a `IncidentService` —`create_incident` y `evaluate_incident_sla`— y los
expone con paridad en REST (`POST /api/v1/incidents`, `GET /api/v1/incidents/{incident_id}/sla`) y
CLI (`create`, `sla`). El alta clasifica el reporte con el triaje canónico, persiste el incidente y
devuelve en la misma respuesta el veredicto de duplicados. La auditoría de SLA evalúa un incidente
almacenado en un instante de referencia, congelando el cómputo en `resolved_at` cuando existe. Toda
regla (similitud, ventana por severidad, clave de grupo, SLA y ventana de cómputo) vive en
`src/domain/`; el adaptador SQLite solo añade columnas, el índice
`idx_incidents_dup_key (duplicate_group_key, status)` y las operaciones de lectura/escritura.

El dominio se amplía con `Incident.recommended_team: Optional[Team]` y
`Incident.duplicate_group_key: Optional[str]`, una evaluación de SLA con contexto
(`SLAEvaluationDetail`) y la normalización temporal centralizada que rechaza instantes aware y
valida `reference_time >= created_at` también para incidentes terminales.

## Contexto Técnico

**Lenguaje / Versión**: Python >= 3.10, gestionado con `uv`; `[tool.uv] package = false` e imports
absolutos desde la raíz del repositorio.

**Dependencias principales**: FastAPI + Pydantic v2 (REST), Typer (CLI), `sqlite3` de la biblioteca
estándar y `difflib`/`SequenceMatcher` del dominio. **Sin dependencias nuevas**; Ruff ya está en el
grupo `dev`.

**Almacenamiento**: SQLite mediante `DATABASE_URL` (por defecto `sqlite:///:memory:`). Tabla
`incidents` ampliada con `recommended_team TEXT` y `duplicate_group_key TEXT`, más el índice
`idx_incidents_dup_key (duplicate_group_key, status)`. Migración idempotente con
`PRAGMA table_info` + `ALTER TABLE`. El alta usa `INSERT` (no `INSERT OR REPLACE`) para que un
identificador existente sea conflicto y nunca sobrescriba.

**Pruebas**: `pytest` con `TestClient` y `CliRunner`; base SQLite de archivo temporal para
persistencia, reinicio y paridad; base en memoria para dominio y caso de uso. Sin `sleep` ni
`datetime.now()` en pruebas de dominio; el reloj se sustituye por instantes inyectados y, cuando el
caso de uso debe resolver el instante actual, se inyecta un `now` explícito en el servicio.

**Plataforma objetivo**: servicio HTTP local/servidor y CLI en Windows/Linux/macOS, ejecutado desde
la raíz del repositorio.

**Tipo de proyecto**: aplicación única Python con dos adaptadores de entrada y uno de salida.

**Objetivos de rendimiento**: alta con veredicto de duplicados y auditoría de SLA por debajo de 1 s
percibido con 10.000 incidentes activos; el alta no debe degradar el resumen de H002.

**Restricciones**: fechas naive consistentes (aware se rechaza); formatos ISO 8601 con `T`;
DTOs de transporte solo en el borde; sin reglas de negocio en aplicación ni adaptadores; serialización
por componente dentro del proceso; Ruff obligatorio (`E4`, `E7`, `E9`, `F`, `TID`).

**Escala / Alcance**: 10.000 incidentes activos, 6 componentes del catálogo cerrado, 4 severidades,
2 estados activos, 2 capacidades nuevas × 2 canales.

## Verificación de la Constitución

*PUERTA: debe pasar antes de la Fase 0. Reevaluada tras el diseño de la Fase 1.*

No se requiere enmienda de la Constitución: el Principio IV ya dispone que "registro y reevaluación
de SLA… DEBEN añadirse como casos de uso cuando su hito los requiera", y el Principio I ya asigna la
detección de duplicados a `src/domain/triage_rules.py`. La decisión estructural
(detección en el dominio + serialización por componente + conflicto de alta por excepción) se
documenta en **ADR-006** dentro del mismo PR, conforme a la puerta 6.

| Principio | Estado | Evidencia o acción requerida |
|---|---|---|
| I. Núcleo determinista único | PASS | `Incident` gana `recommended_team` y `duplicate_group_key`; `SLAEvaluationDetail` y la ventana de cómputo viven en `models.py`; similitud, ventana por severidad y clave de grupo en `triage_rules.py`. Ningún DTO ni fila SQL redeclara reglas. |
| II. Dominio puro y auditable | PASS | Solo `dataclasses`, `datetime`, `difflib`, `types`, `typing`. Sin reloj, sin E/S, sin `print`. La normalización temporal es una función pura y determinista; el `now` entra desde el caso de uso. |
| III. Arquitectura hexagonal estricta | PASS | `adapters → application → domain`. El adaptador SQLite no calcula similitud ni SLA; el servicio solo valida, serializa por componente, secuencia y traduce errores. |
| IV. Puertos explícitos y composición única | PASS (sin enmienda) | `IncidentRepositoryPort` conserva sus cinco métodos; se precisa la semántica de `save_incident` (inserta y rechaza conflicto) sin cambiar la firma. `factory.py` sigue siendo la única raíz de composición. |
| V. Stack gobernado | PASS | Sin dependencias nuevas; `difflib` y `sqlite3` son biblioteca estándar. |
| VI. Fronteras verificadas con Ruff | PASS | Se mantienen `pyproject.toml` y los `ruff.toml` jerárquicos; el contrato de ciclo de vida vive en `inbound/` y el CLI no importa `api/`. |
| VII. BDD y pruebas ejecutables | PASS | `tests/test_spec_003_lifecycle_sla.py` con los cinco bloques de aceptación (alta, duplicados, SLA, paridad/errores, fronteras y concurrencia); pruebas de dominio para similitud, ventana y normalización temporal; pruebas del adaptador para columnas, índice y conflicto. |
| Invariantes de SLA | PASS | Se reutiliza `SLA_POLICY_TABLE` sin cambios (P0 60/P1 240 24x7; P2 480/P3 1440 hábiles; 75 %; incumplimiento estricto). El cómputo termina en `resolved_at` y el resultado congela sus valores. |
| Estados del incidente | PASS | El alta inicia siempre en `OPEN`; terminales exigen `resolved_at`, no escalan y no entran en la detección de duplicados. |
| Deuda deliberada | PASS | `legacy/triage_rules.py` sigue congelado; los festivos siguen sin descontarse (ADR-002). La entrada de `AGENTS.md` que afirmaba `duplicate_group_key` siempre `null` se actualiza en este PR, porque H003 cierra esa deuda. |
| Gobernanza documental | PASS | ADR-006 con Mermaid, actualización de `AGENTS.md`, `README.md`, `docs/ROADMAP.md` (H003 → implementado) y `docs/adr/002` si la precisión temporal lo amerita. `CONTEXT_LOG.md` y `SDD_LOG.md` no se reescriben. |

**Reevaluación tras el diseño de la Fase 1**: se mantiene. Los contratos nuevos no introducen capas,
dependencias ni tipos de dominio paralelos; `inbound/lifecycle_contract.py` es un contrato de
transporte compartido (precedente: `summary_contract.py` y `problem.py`) y no crea una arista entre
adaptadores concretos.

## Estructura del Proyecto

### Documentación (esta funcionalidad)

```text
specs/003-incident-lifecycle-sla/
├── plan.md                          # Este documento
├── research.md                      # Fase 0 · decisiones y alternativas
├── data-model.md                    # Fase 1 · entidades, esquema SQLite e invariantes
├── quickstart.md                    # Fase 1 · guía de validación ejecutable
├── contracts/
│   ├── create-api.md                # POST /api/v1/incidents
│   ├── sla-api.md                   # GET /api/v1/incidents/{incident_id}/sla
│   ├── lifecycle-cli.md             # create y sla
│   ├── incident-created.schema.json # Documento canónico del alta
│   └── sla-evaluation.schema.json   # Documento canónico de SLA
└── tasks.md                         # Fase 2 (/speckit.tasks), no se crea aquí
```

### Código fuente (raíz del repositorio)

```text
src/
├── domain/
│   ├── models.py                    # MODIFICADO · Incident + recommended_team/duplicate_group_key;
│   │                                #            SLAEvaluationDetail + SLAComputationWindow
│   ├── triage_rules.py              # MODIFICADO · umbral, ventana por severidad,
│   │                                #            DuplicateAssessment y assess_duplicates
│   └── sla_calculator.py            # MODIFICADO · normalización temporal única y
│                                    #            evaluate_sla_detail (ventana + contexto)
├── application/
│   └── services.py                  # MODIFICADO · create_incident, evaluate_incident_sla,
│                                    #            IncidentNotFoundError, IncidentAlreadyExistsError,
│                                    #            serialización por componente, now inyectable
├── adapters/
│   ├── inbound/
│   │   ├── temporal_contract.py     # NUEVO · validación ISO 8601 naive compartida
│   │   ├── lifecycle_contract.py    # NUEVO · CreateIncidentRequest, IncidentCreatedResponse,
│   │   │                            #         SLAEvaluationResponse y mapeos
│   │   ├── summary_contract.py      # MODIFICADO · delega el parseo en temporal_contract
│   │   ├── api/schemas.py           # MODIFICADO · reexporta/usa los DTOs del contrato
│   │   ├── api/app.py               # MODIFICADO · las dos rutas nuevas
│   │   ├── api/errors.py            # MODIFICADO · prefijo por ruta, 404 y 422 incoherente
│   │   ├── problem.py               # MODIFICADO · títulos de los códigos nuevos
│   │   └── cli.py                   # MODIFICADO · subcomandos create y sla
│   └── outbound/
│       └── sqlite_repository.py     # MODIFICADO · columnas, migración, índice dup_key,
│                                    #            INSERT con conflicto, mapeo ampliado
tests/
├── test_spec_003_lifecycle_sla.py   # NUEVO · los cinco bloques BDD con TestClient y CliRunner
├── domain/
│   ├── test_duplicate_rules.py      # NUEVO · similitud, ventana, orden y herencia de clave
│   └── test_sla_calculator.py       # MODIFICADO · normalización temporal y SLA congelado
├── application/
│   └── test_services.py             # MODIFICADO · create/sla, códigos y serialización
└── adapters/
    ├── test_sqlite_repository.py    # MODIFICADO · columnas, índice, conflicto y duplicados
    └── test_api.py / test_cli.py    # MODIFICADO · contratos de las rutas y comandos nuevos
docs/adr/006-ciclo-vida-duplicados-sla.md  # NUEVO · ADR del hito con Mermaid
AGENTS.md, README.md, docs/ROADMAP.md      # MODIFICADOS · comandos, códigos y estado del hito
```

**Decisión de estructura**: se mantiene un único proyecto Python. El dominio concentra las reglas
nuevas (equivalencia, ventana, clave de grupo, ventana de cómputo y normalización temporal); la
aplicación solo valida, serializa por componente, secuencia y traduce errores; el inbound comparte un
contrato de transporte explícito entre HTTP y CLI sin que el CLI importe `api/`; el outbound conserva
todo el SQL, el DDL y el mapeo fila → entidad.

## Fase 0 · Investigación

Salida: [research.md](./research.md). No quedan `NEEDS CLARIFICATION`; las decisiones abiertas se
resuelven con estas elecciones y su justificación:

| # | Decisión | Motivo central |
|---|---|---|
| D1 | `Incident.recommended_team: Optional[Team]` y `duplicate_group_key: Optional[str]` | Cierra el contrato persistido de la spec sin duplicar el catálogo (`Team`, no un alias `TeamName`) |
| D2 | Normalización temporal única en `sla_calculator.py` que **rechaza** aware y valida `reference_time >= created_at` | Cumple FR-022/FR-024 y evita comparaciones naive/aware; no se convierte a UTC |
| D3 | `SLAEvaluationDetail` (incidente + evaluación + `reference_time` + ventana) y `evaluate_sla_detail` | FR-018 exige contexto y ventana; `SLAEvaluation` de H002 queda intacto |
| D4 | Equivalencia de duplicados en `triage_rules.py` (`difflib`, umbral 0.75, ventana por severidad del más antiguo) | El Principio I asigna los duplicados al dominio; el adaptador no puede decidir similitud |
| D5 | `find_open_duplicates` entrega candidatos estructurales (activos, mismo componente, distinto id) | Mantiene la firma de H002 y la regla en un solo lugar |
| D6 | `save_incident` usa `INSERT` y traduce `IntegrityError` a `IncidentAlreadyExistsError` | FR-008/FR-016: conflicto sin sobrescritura y alta atómica |
| D7 | Serialización por componente con cerrojos en proceso dentro de `IncidentService` | FR-030 con el supuesto de almacenamiento único y sin bloqueo distribuido; sin puerto especulativo |
| D8 | `DataInconsistencyError` gana `status` opcional (409 por defecto) | FR-022 exige 422 en HTTP con salida 1 en CLI; el resumen conserva su 409 |
| D9 | Contrato compartido `inbound/lifecycle_contract.py` + `temporal_contract.py` | Paridad verificable y un único parser ISO 8601 para los dos canales |
| D10 | Códigos estables `CREATE_*` y `SLA_*`; 404 para inexistente | Traducción por ruta sin reutilizar códigos de triaje o resumen |
| D11 | Pruebas de concurrencia y volumen fuera de aserciones de tiempo | Determinismo en CI; el tiempo se reporta como evidencia del PR |

## Fase 1 · Diseño y Contratos

Salidas: [data-model.md](./data-model.md), [contracts/create-api.md](./contracts/create-api.md),
[contracts/sla-api.md](./contracts/sla-api.md),
[contracts/lifecycle-cli.md](./contracts/lifecycle-cli.md),
[contracts/incident-created.schema.json](./contracts/incident-created.schema.json),
[contracts/sla-evaluation.schema.json](./contracts/sla-evaluation.schema.json) y
[quickstart.md](./quickstart.md).

Puntos contractuales fijados:

- **Alta**: `POST /api/v1/incidents` → `201`; cuerpo `{incident_id, raw_text, title?, created_at?}`
  con `extra="forbid"`; respuesta con datos del incidente clasificado, `duplicate_group_key`,
  `is_duplicate` y `duplicate_of`. Un identificador existente → `409 CREATE_ID_CONFLICTO`.
- **SLA**: `GET /api/v1/incidents/{incident_id}/sla?reference_time=...` → `200`; sin
  `reference_time` rige el instante actual informado en la respuesta; identificador inexistente →
  `404 SLA_INCIDENTE_NO_ENCONTRADO`; referencia anterior a la creación → `422
  SLA_REFERENCIA_INCONSISTENTE` (CLI salida 1); entrada malformada → `422` (CLI salida 2).
- **CLI**: `create --incident-id ... (--raw-text ...|--raw-text -|--file ...) [--title ...]
  [--created-at ...]` y `sla --incident-id ... [--reference-time ...]`; JSON idéntico al HTTP,
  serializado con `model_dump(mode="json")` para que las fechas coincidan byte a byte.
- **Duplicados**: `duplicate_of` ordenado del más antiguo al más reciente (desempate por
  identificador ascendente); sólo equivalentes previos; `duplicate_group_key` nula si
  `duplicate_of` está vacío y, en caso contrario, el identificador del original más antiguo o la
  clave heredada de su grupo.
- **SLA congelado**: en estados terminales el fin del cómputo es `resolved_at`, con independencia de
  que `reference_time` sea anterior o posterior a la resolución; `reference_time` sólo debe ser
  posterior o igual a `created_at`.
- **Ventana de cómputo**: `window` vale `"24x7"` (P0/P1) o `"BUSINESS_HOURS"` (P2/P3) y se deriva de
  `SLARule.operates_24x7`, nunca del adaptador.

## Orden de Implementación

1. **Dominio**: ampliar `Incident`; añadir `SLAComputationWindow`, `SLAEvaluationDetail` y
   `evaluate_sla_detail`; centralizar `validar_instante_naive` y `resolver_ventana_temporal`; añadir
   `DUPLICATE_SIMILARITY_THRESHOLD`, `DUPLICATE_WINDOW_DAYS`, `DuplicateAssessment`,
   `is_equivalent` y `assess_duplicates`.
2. **Aplicación**: añadir `IncidentAlreadyExistsError`, `IncidentNotFoundError`,
   `IncidentCreationResult`, `create_incident` y `evaluate_incident_sla`; inyectar `now` como
   callable opcional; mantener el reporte de duplicados fuera del dominio de transporte.
3. **Salida**: extender el esquema y la migración; crear el índice `idx_incidents_dup_key`; cambiar
   la escritura a `INSERT` con traducción de conflicto; mapear las columnas nuevas en lectura y
   escritura; sembrar duplicados sintéticos solo en el seeder del benchmark.
4. **Entrada**: crear `temporal_contract.py` y `lifecycle_contract.py`; registrar los dos endpoints,
   ampliar el prefijo de errores por ruta y los títulos de `problem.py`; añadir los subcomandos
   `create` y `sla` con sus códigos de salida.
5. **Pruebas**: cinco bloques BDD de la spec; unitarias de dominio (similitud en el umbral 0,75,
   ventana exacta, grupo heredado, SLA congelado, `reference_time` anterior a creación, aware
   rechazado); aplicación (códigos y serialización); adaptador (columnas, índice, conflicto,
   candidatos); concurrencia con dos hilos y base de archivo.
6. **Validación**: `uv run ruff check src/` y `uv run pytest -v`; comprobar el plan de consulta del
   índice nuevo con `EXPLAIN QUERY PLAN` y el alta/SLA con 10.000 activos.
7. **Gobernanza**: ADR-006 con Mermaid; actualizar `AGENTS.md`, `README.md` y `docs/ROADMAP.md`;
   retirar de `AGENTS.md` la afirmación de que `duplicate_group_key` permanece `null`.

## Seguimiento de Complejidad

| Desviación | Por qué se necesita | Alternativa más simple rechazada |
|---|---|---|
| Cerrojos por componente en `IncidentService` (estado mutable en la aplicación) | FR-030 exige que detección y alta se serialicen por componente; el supuesto excluye bloqueo distribuido y el servicio ya es el único punto que secuencia y transacciona | Bloquear dentro del adaptador: no cubriría la detección, que es del dominio; añadir un `ComponentLockPort`: abstracción especulativa para un único proceso |
| `DataInconsistencyError.status` opcional | FR-022 pide `422` en HTTP y salida `1` en CLI, combinación que el 409 fijo de H002 no representa | Nueva clase de error + manejador HTTP propio: duplica el documento problem+json y la traducción de la CLI |
| `save_incident` cambia de `INSERT OR REPLACE` a `INSERT` con conflicto | FR-008/FR-016: el alta nunca debe sobrescribir ni fusionar; el `REPLACE` silencioso violaría el invariante | Pre-consulta `get_incident` en el servicio: carrera entre comprobación e inserción y dos lecturas por alta |
| Duplicados evaluados en el dominio aunque el adaptador expone `find_open_duplicates` | El Principio I asigna la detección a `triage_rules.py`; la similitud y la ventana no son filtros estructurales | Implementar `SequenceMatcher` en SQL/Python dentro del adaptador: duplicaría la regla y rompería la paridad ante un futuro adaptador PostgreSQL |

## Riesgos y Mitigaciones

| Riesgo | Mitigación |
|---|---|
| Cerrojos en proceso no cubren dos procesos concurrentes | Documentado como supuesto de la spec (almacenamiento único, sin réplicas); el `INSERT` con clave primaria sigue impidiendo sobrescrituras y ADR-006 fija el límite |
| `:memory:` privado por conexión rompe la verificación de reinicio | Las pruebas de persistencia, reinicio y paridad usan archivo temporal y lo eliminan al terminar |
| Fechas aware colándose por `created_at` o `reference_time` | Un único `temporal_contract` en el borde y una única normalización en el dominio; las pruebas cubren ambos canales y los dos campos |
| Cambiar `requires_escalation` o el cómputo al refactorizar la evaluación | `evaluate_sla_status` conserva su firma y su aritmética; H002 y sus pruebas deben seguir en verde sin cambios de valores |
| El `INSERT` rompe el seeder del benchmark al reutilizar una base | El seeder conserva una sentencia propia de siembra idempotente; la ruta de alta usa `INSERT` estricto y tiene prueba de conflicto |
| Divergencia de formato de fechas entre HTTP y CLI | Ambos serializan el mismo modelo con `model_dump(mode="json")` y la prueba de paridad compara documentos por igualdad estricta |
| Índice nuevo sin uso real | Se verifica con `EXPLAIN QUERY PLAN` la consulta por `duplicate_group_key`/`status` y se documenta que la ruta de alta no lo necesita para decidir equivalencia |

## Criterios de Cierre

- `uv run pytest -v` en verde, incluidos H001 y H002 sin cambios de comportamiento.
- `uv run ruff check src/` sin errores con `TID251`/`TID252` activos.
- `tests/test_spec_003_lifecycle_sla.py` cubre los cinco bloques BDD y la paridad HTTP/CLI de alta
  y SLA por igualdad estricta de documentos.
- Alta con 10.000 activos y auditoría de SLA dentro del objetivo de `SC-006`, con evidencia de
  `EXPLAIN QUERY PLAN` del índice `idx_incidents_dup_key`.
- Ningún incidente previo se modifica al registrar un duplicado; el conflicto de identificador no
  sobrescribe (prueba explícita de FR-008 y SC-008).
- ADR-006, `AGENTS.md`, `README.md` y `docs/ROADMAP.md` actualizados en el mismo PR.
