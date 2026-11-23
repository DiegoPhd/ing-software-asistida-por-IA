# Plan de Implementación: Resumen de Incidentes Activos (H002)

**Rama de trabajo**: `diego.betancourt/reto-4` · **Rama de entrega H002**: `diego.betancourt/reto-N` (pendiente de asignación)

**Fecha**: 2026-11-22 | **Spec**: [spec.md](./spec.md)

**Entrada**: Especificación `specs/001-active-incidents-summary/spec.md` y diseño del Hito 002 solicitado por el usuario.

## Resumen

H002 expone el mismo caso de uso `IncidentService.get_active_incidents_summary` a REST y CLI. El resumen (total activo, total incumplido y detalle ordenado con minutos de SLA y escalamiento) se calcula en el dominio, la persistencia SQLite optimizada (`INNER JOIN sla_policies` + índice compuesto `(component, status)`) vive detrás de `IncidentRepositoryPort`, y el ensamblaje se concentra en la fábrica de adaptadores de salida. La entrega migra el cálculo de SLA y los tipos duplicados a `src/domain/`, retira el legado `src/models.py`, `src/sla_calculator.py` y `src/incident_repository.py`, e incorpora la verificación estática de fronteras con Ruff.

Este hito es exactamente el refactor de Fase 2 previsto: la deuda deliberada de `SELECT *`, filtrado en Python y N+1 se cierra en el nuevo adaptador SQLite y no se replica en ninguna otra capa.

## Contexto Técnico

**Lenguaje / Versión**: Python >= 3.10, gestionado con `uv`; `[tool.uv] package = false` e imports absolutos desde la raíz.

**Dependencias principales**: FastAPI + Pydantic v2 (REST), Typer (CLI), `sqlite3` de la biblioteca estándar. Sin dependencias nuevas; Ruff ya está en el grupo `dev`.

**Almacenamiento**: SQLite mediante `DATABASE_URL`, por defecto `sqlite:///:memory:`. Esquema `incidents` y `sla_policies`, índice compuesto `idx_incidents_component_status (component, status)`. Una sola conexión por repositorio con `check_same_thread=False` y cerrojo de acceso.

**Pruebas**: `pytest` con `TestClient` y `CliRunner`; base SQLite temporal por prueba para la paridad HTTP/CLI y base en memoria para las pruebas de dominio y de caso de uso.

**Plataforma objetivo**: servicio HTTP local/servidor y CLI en Windows/Linux/macOS (el repositorio se ejecuta desde su raíz).

**Tipo de proyecto**: aplicación única Python con dos adaptadores de entrada y uno de salida.

**Objetivos de rendimiento**: resumen de 10.000 incidentes en menos de 1 s; una sola consulta SQL por resumen, sin N+1; consulta filtrada resuelta por el índice compuesto.

**Restricciones**: fechas naive consistentes; `reference_time` opcional en ISO 8601 sin zona; DTOs de transporte mapeados en el borde; sin reglas de negocio en aplicación ni adaptadores; Ruff obligatorio (`E4`, `E7`, `E9`, `F`, `TID`).

**Escala / Alcance**: 10.000 incidentes almacenados; cuatro severidades; dos estados activos; una capacidad nueva con dos interfaces.

## Verificación de la Constitución

*PUERTA: debe pasar antes de la Fase 0. Reevaluada tras el diseño de la Fase 1.
La fila IV se aprueba con la enmienda MINOR 1.1.0 (ADR-005, T039); hasta su
ratificación el plan queda BLOQUEADO y no se inicia la Fase 0.*

| Principio | Estado | Evidencia o acción requerida |
|---|---|---|
| I. Núcleo determinista único | PASS | `Incident`, `IncidentStatus`, `SLARule`, `SLAEvaluation` y `evaluate_sla_status` pasan a `src/domain/models.py` y `src/domain/sla_calculator.py`. Se eliminan `src/models.py` y `src/sla_calculator.py`; no quedan tipos duplicados. |
| II. Dominio puro y auditable | PASS | El dominio nuevo solo usa `dataclasses`, `datetime`, `typing` y `math`; sin reloj implícito, sin E/S, sin `print`. El `main()` de demostración del SLA sale del dominio y se retira con el legado. |
| III. Arquitectura hexagonal estricta | PASS | Dependencia `adapters → application → domain`. El identificador `component` viaja como texto plano hasta el puerto; el adaptador SQLite reconstruye entidades; los DTOs de FastAPI/Pydantic viven solo en `inbound`. |
| IV. Puertos explícitos y composición única | PASS (enmienda 1.1.0) | Se define solo `IncidentRepositoryPort` y la raíz de composición se mueve a `src/adapters/outbound/factory.py`; la enmienda MINOR 1.1.0 (ADR-005, T039) ratifica ambos cambios. Ver Seguimiento de Complejidad. |
| V. Stack gobernado | PASS | Sin dependencias nuevas; `sqlite3` estándar y Ruff ya declarado. |
| VI. Fronteras verificadas con Ruff | PASS | `[tool.ruff.lint]` raíz y `src/domain/ruff.toml`, `src/application/ruff.toml`, `src/adapters/inbound/ruff.toml` con `extend` y `TID251`/`TID252`. |
| VII. BDD y pruebas ejecutables | PASS | `tests/test_spec_002_summary.py` con escenarios Dado/Cuando/Entonces, paridad REST/CLI, fronteras de SLA y verificación de cumplimiento del puerto. |
| Invariantes de SLA | PASS | Se reutilizan sin cambios: P0 60/P1 240 24x7; P2 480/P3 1440 en ventana hábil; incumplimiento estricto; escalamiento al 75 % solo en estados activos. |
| Deuda deliberada | PASS | El N+1 se elimina porque H002 es el refactor previsto; no se traslada al dominio ni se replica en otros adaptadores. `legacy/triage_rules.py` sigue congelado. |
| Gobernanza documental | PASS | README, AGENTS.md, ROADMAP y ADR-002 se actualizan en el mismo PR; ADR-005 documenta la topología con Mermaid. |

**Decisiones estructurales ratificadas por la enmienda 1.1.0** (detalle en Seguimiento de Complejidad):

1. Se declara un solo puerto (`IncidentRepositoryPort`) en H002; `SlaPolicyPort` y `ClockPort` quedan para hitos posteriores.
2. `src/adapters/outbound/factory.py` asume la raíz de composición y `src/composition.py` se retira.
3. Se retira la deuda N+1 intencional, por ser el objeto mismo de H002.

**Reevaluación tras el diseño de la Fase 1**: el resultado se mantiene. Los contratos no añaden dependencias ni capas nuevas; la enmienda MINOR 1.1.0 de la Constitución y el ADR-005 quedan registrados en el mismo PR. El contrato compartido de `inbound/summary_contract.py` no crea una arista entre adaptadores concretos, y la prueba de cumplimiento del puerto no requiere dependencias adicionales.

## Estructura del Proyecto

### Documentación (esta funcionalidad)

```text
specs/001-active-incidents-summary/
├── plan.md              # Este documento
├── research.md          # Fase 0 · decisiones y alternativas
├── data-model.md        # Fase 1 · entidades, esquema SQLite e invariantes
├── quickstart.md        # Fase 1 · guía de validación ejecutable
├── contracts/
│   ├── summary-api.md   # Contrato HTTP
│   ├── summary-cli.md   # Contrato de consola
│   └── summary.schema.json  # Documento JSON canónico compartido
├── checklists/
│   └── requirements.md
└── tasks.md             # Fase 2 (/speckit.tasks), no se crea aquí
```

### Código fuente (raíz del repositorio)

```text
src/
├── domain/
│   ├── models.py                    # NUEVO · entidades; el resumen se construye en sla_calculator.py
│   ├── sla_calculator.py            # NUEVO · política y evaluate_sla_status (migrado de src/sla_calculator.py)
│   ├── severity.py                  # existente
│   ├── triage.py                    # existente (H001, sin cambios)
│   └── ruff.toml                    # NUEVO · fronteras del dominio
├── application/
│   ├── ports.py                     # NUEVO · IncidentRepositoryPort (Protocol)
│   ├── services.py                  # MODIFICADO · get_active_incidents_summary
│   └── ruff.toml                    # NUEVO · fronteras de aplicación
├── adapters/
│   ├── inbound/
│   │   ├── api/app.py               # MODIFICADO · GET /api/v1/incidents/summary
│   │   ├── api/errors.py            # MODIFICADO · handler de datos inconsistentes
│   │   ├── cli.py                   # MODIFICADO · subcomando summary
│   │   ├── summary_contract.py      # NUEVO · ActiveIncidentItem, ActiveIncidentsSummaryResponse y mapeo
│   │   ├── problem.py               # MODIFICADO · títulos de los códigos nuevos
│   │   └── ruff.toml                # NUEVO · fronteras del inbound
│   └── outbound/
│       ├── sqlite_repository.py     # NUEVO · SQLiteIncidentRepository + índice + benchmark __main__
│       └── factory.py               # NUEVO · selección por DATABASE_URL y ensamblaje
├── composition.py                   # SE RETIRA · su papel pasa a adapters/outbound/factory.py
├── models.py                        # SE RETIRA · legado duplicado
├── sla_calculator.py                # SE RETIRA · legado duplicado
└── incident_repository.py           # SE RETIRA · legado con N+1

tests/
├── test_spec_001_triage.py          # existente, sigue en verde
├── test_spec_002_summary.py         # NUEVO · BDD de la spec 002 + cumplimiento del puerto
├── domain/test_sla_calculator.py    # NUEVO · tabla de fronteras de SLA (ADR-002)
└── adapters/                        # existente
    └── test_sqlite_repository.py    # NUEVO · puerto, consulta única e índice

tools/
└── benchmark_summary.py             # NUEVO · benchmark de extremo a extremo (no pytest)

docs/adr/005-resumen-activos-hexagonal.md   # NUEVO · ADR del hito con Mermaid
pyproject.toml                              # MODIFICADO · configuración Ruff
```

**Decisión de estructura**: se mantiene un único proyecto Python. El dominio concentra entidades y reglas; la aplicación solo declara el puerto y orquesta; el inbound comparte un contrato de transporte explícito entre HTTP y CLI (precedente: `problem.py` de H001) sin que un adaptador concreto dependa de otro; el outbound contiene todo el SQL, el DDL, la siembra de políticas y el mapeo fila → entidad.

## Fase 0 · Investigación

Salida: [research.md](./research.md). No quedan `NEEDS CLARIFICATION`; las decisiones abiertas se resuelven con estas elecciones y su justificación:

| # | Decisión | Motivo central |
|---|---|---|
| D1 | Migrar SLA y tipos a `src/domain/` y retirar el legado | Elimina la duplicación y cumple el Principio I |
| D2 | Resumen calculado en el dominio (`summarize_active_incidents`) | Totales, orden y banderas son reglas, no orquestación |
| D3 | Puerto con cinco métodos y cumplimiento estructural verificable | Contrato de H002/H003 sin herencia obligatoria |
| D4 | SQLite con `INNER JOIN` + índice `(component, status)` y una sola consulta | Cierra el N+1 y sostiene las 10.000 filas |
| D5 | Fábrica de salida como raíz de composición y retiro de `composition.py` | Único punto de ensamblaje, sin dos formas competidoras |
| D6 | Contrato JSON compartido en `inbound/summary_contract.py` | Paridad verificable entre HTTP y CLI |
| D7 | `reference_time` ISO 8601 naive, opcional; por defecto el instante actual | Determinismo y coherencia con el invariante de fechas |
| D8 | Base de archivo temporal para pruebas de paridad; memoria para dominio | Un `:memory:` por conexión no se comparte entre procesos |
| D9 | Conteo de consultas + `EXPLAIN QUERY PLAN` y benchmark de canales fuera de pytest | Evita pruebas de tiempo frágiles en CI y cubre SC-001 de extremo a extremo |

## Fase 1 · Diseño y Contratos

Salidas: [data-model.md](./data-model.md), [contracts/summary-api.md](./contracts/summary-api.md), [contracts/summary-cli.md](./contracts/summary-cli.md), [contracts/summary.schema.json](./contracts/summary.schema.json) y [quickstart.md](./quickstart.md).

Puntos contractuales fijados:

- **Documento canónico**: `total_active`, `breached_count` e `incidents[]`; cada ítem expone `incident_id`, `title`, `component`, `severity`, `status`, `elapsed_minutes`, `is_breached` y `requires_escalation`.
- **HTTP**: `GET /api/v1/incidents/summary?component={componente}&reference_time={ISO-8601}`; `200` con totales en cero e `incidents` vacío cuando no hay coincidencias.
- **CLI**: `summary [--component ...] [--reference-time ...]`; JSON idéntico por `stdout`; códigos de salida `0` éxito, `2` entrada inválida, `1` error inesperado o dato inconsistente.
- **Errores estables**: `SUMMARY_COMPONENTE_DEMASIADO_LARGO`, `SUMMARY_REFERENCIA_INVALIDA`, `SUMMARY_SOLICITUD_INVALIDA`, `SUMMARY_REFERENCIA_INCONSISTENTE` y `SUMMARY_ERROR_INTERNO`, reutilizados por ambos canales con `application/problem+json` / `stderr`.
- **Orden**: severidad `P0`→`P3`, luego minutos transcurridos descendentes, luego `incident_id` ascendente.

## Orden de Implementación

1. **Dominio**: crear `models.py` y `sla_calculator.py` con la política de ADR-002, `evaluate_sla_status` y `summarize_active_incidents`; unificar `IncidentStatus` con `IN_PROGRESS` y hacer que el escalamiento exija estado activo.
2. **Aplicación**: añadir `ports.py` y el método `get_active_incidents_summary` con validación de filtro e instante.
3. **Salida**: implementar `SQLiteIncidentRepository` (esquema, índice, `INNER JOIN`, UPSERT, salud, candidatos de duplicados) y `factory.py` con el análisis de `DATABASE_URL`.
4. **Entrada**: contrato compartido, endpoint REST y subcomando `summary`, con mapeo del resumen y traducción de errores.
5. **Retiro del legado**: eliminar `src/models.py`, `src/sla_calculator.py`, `src/incident_repository.py` y `src/composition.py`; actualizar todos los imports y mover el benchmark al adaptador de salida.
6. **Ruff**: configurar la raíz y los tres `ruff.toml`; ejecutar `uv run ruff check src/` y corregir hallazgos sin `# noqa`.
7. **Pruebas**: BDD de la especificación, fronteras de SLA, cumplimiento del puerto, conteo de consultas y plan de consulta con índice.
8. **Documentación y gobernanza**: ADR-005 con Mermaid, enmienda MINOR 1.1.0 de la Constitución, actualización de ADR-002, README, AGENTS.md y ROADMAP.

## Seguimiento de Complejidad

| Desviación | Por qué se necesita | Alternativa más simple rechazada |
|---|---|---|
| Un solo puerto (`IncidentRepositoryPort`) frente a los tres que nombra la Constitución §IV | La política de SLA es una constante pura del dominio (ADR-002) y el instante de referencia es un argumento explícito del caso de uso; `SlaPolicyPort` y `ClockPort` no tendrían llamador, ni prueba, ni implementación real en H002 | Declarar Protocols vacíos o con implementaciones ficticias: sería abstracción especulativa, sin uso y sin verificación; se incorporarán cuando H003/H004 los requieran |
| Raíz de composición en `src/adapters/outbound/factory.py` y retiro de `src/composition.py` | El hito exige seleccionar el repositorio por `DATABASE_URL` y el inbound no puede instanciar adaptadores concretos; mantener ambos módulos crea dos raíces competidoras | Conservar `composition.py` como único ensamblador y hacer que la fábrica solo devuelva clases: la selección por DSN seguiría instanciando en la fábrica y el inbound acabaría conociendo el repositorio |
| Retiro de la deuda N+1 de `get_active_incidents_summary` | H002 es el refactor de Fase 2: el resumen debe responder sobre 10.000 filas y la deuda solo podía vivir en el adaptador de persistencia | Mantener el método legado como segunda implementación del mismo resumen: violaría la unicidad de la capacidad (Principio III y gobernanza) y dejaría dos resultados competidores |

**Remediación de gobernanza obligatoria en el PR**: ADR-005 (topología, puerto y raíz de composición, con Mermaid) y enmienda MINOR 1.1.0 a `docs/constitution.md` y `.specify/memory/constitution.md` para nombrar la fábrica de salida como raíz de composición y el conjunto de puertos vigente en H002. Sin esa enmienda, el PR no cumple la puerta de gobernanza.

## Riesgos y Mitigaciones

| Riesgo | Mitigación |
|---|---|
| `:memory:` no se comparte entre conexiones o procesos | La app y la CLI usan la misma URL; las pruebas de paridad usan archivo temporal y las de dominio inyectan el repositorio en el servicio |
| Conexión SQLite usada desde el hilo del `TestClient` | `check_same_thread=False` y cerrojo de acceso en el repositorio, con una conexión por instancia |
| Reglas de SLA duplicadas al migrar | El adaptador no calcula SLA: solo filtra y mapea; toda evaluación ocurre en `src/domain/sla_calculator.py` |
| Ruff descubre hallazgos preexistentes al activar `E4/E7/E9/F` | Se corrigen en el mismo PR; no se desactivan reglas ni se usa `# noqa` |
| `find_open_duplicates` se interpreta como detección completa de H003 | El puerto y el adaptador entregan candidatos activos del mismo componente; similitud y ventana se implementan en H003 sin cambiar la firma |

## Criterios de Cierre

- `uv run pytest -v` en verde, incluidos H001 y los nuevos escenarios.
- `uv run ruff check src/` sin errores con `TID251`/`TID252` activos.
- `uv run pytest tests/test_spec_002_summary.py tests/adapters/test_sqlite_repository.py` demuestra paridad JSON, conteo de una sola consulta y uso del índice.
- El resumen de 10.000 incidentes se valida con el benchmark del adaptador y con la medición de extremo a extremo HTTP/CLI (`tools/benchmark_summary.py`) dentro del objetivo de `SC-001`.
- No quedan imports ni puntos de entrada al legado retirado; `legacy/triage_rules.py` sigue sin importarse.
- ADR-005, enmienda de la Constitución y documentación operativa actualizados en el mismo PR.
