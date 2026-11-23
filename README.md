# IncidentOps — Proyecto Semilla (Semana 1)

**IncidentOps** es un sistema backend en Python gestionado con [`uv`](https://docs.astral.sh/uv/) que administra reportes de incidentes de software, evalúa acuerdos de nivel de servicio (**SLA**) sobre SQLite y ejecuta reglas de **triaje y enrutamiento de tickets**.

Este repositorio sirve como banco de pruebas práctico para la **Semana 1** de *Ingeniería de Software Asistida por Inteligencia Artificial (ISIA)* bajo un enfoque **100% *AI for Software Engineering***.

---

## Requisitos e Instalación con `uv`

- **Python 3.10+** y **[`uv`](https://docs.astral.sh/uv/)**.
- Dependencias declaradas en [`pyproject.toml`](pyproject.toml):
  - `fastapi` + `pydantic` v2: canal HTTP.
  - `typer`: canal de consola.
  - `tiktoken`: medición de tokens BPE (`o200k_base` / `cl100k_base`) en las estrategias de contexto.

```bash
uv sync
```

Todos los comandos se ejecutan desde la raíz del repositorio con `uv run`.

---

## Arquitectura (hexagonal)

```text
src/
├── domain/                 # Núcleo puro: sin frameworks, reloj ni E/S
│   ├── models.py           # Incident, SLAEvaluation, SLAEvaluationDetail, derivar_titulo
│   ├── sla_calculator.py   # política, evaluación con contexto y resumen
│   ├── severity.py         # catálogo cerrado de severidades, equipos y componentes
│   └── triage_rules.py     # triaje (H001) y equivalencia de duplicados (H003)
├── application/
│   ├── ports.py            # IncidentRepositoryPort y ClockPort (Protocol)
│   └── services.py         # IncidentService: triaje, alta, resumen y SLA
└── adapters/
    ├── inbound/            # api/app.py · cli.py · contracts · problem.py
    └── outbound/           # sqlite_repository.py · system_clock.py · factory.py
```

- Los adaptadores de entrada solo conocen el caso de uso, el contrato de
  transporte compartido y la fábrica de salida.
- `src/adapters/outbound/factory.py` es el único punto que instancia clases
  concretas, selecciona el repositorio por `DATABASE_URL` e inyecta
  `SystemClock` a través de `ClockPort`.
- Las fronteras se verifican con Ruff (`TID251`/`TID252`) mediante
  `src/domain/ruff.toml`, `src/application/ruff.toml` y
  `src/adapters/inbound/ruff.toml`.
- Decisiones: [ADR-002](docs/adr/002-calculo-sla-horario-habil.md),
  [ADR-003](docs/adr/003-arquitectura-hexagonal.md),
  [ADR-004](docs/adr/004-contrato-interfaces-h001.md),
  [ADR-005](docs/adr/005-resumen-activos-hexagonal.md) y
  [ADR-006](docs/adr/006-ciclo-vida-duplicados-sla.md).

---

## 1. Auditoría de Tokens con `tiktoken`

Compara cuántos tokens consume leer todo el repositorio, leer los `.py`
coincidentes o extraer únicamente la definición, firmas y referencias de un
símbolo (estilo LSP):

```bash
uv run python -m src.context_audit --symbol evaluate_sla_status
uv run python -m src.context_audit --symbol get_active_incidents_summary
uv run python -m src.context_audit --symbol classify_impact
uv run python -m src.context_audit --compare-formats
```

---

## 2. H001 · Triaje por HTTP y CLI

El motor de triaje vive en `src/domain/triage_rules.py` y se expone a través de un
único caso de uso (`IncidentService.triage_incident`) consumido por dos
adaptadores. La operación es stateless: no lee ni escribe base de datos.

**CLI (Typer):**

```bash
uv run python -m src.adapters.inbound.cli triage --incident-id INC-1001 --raw-text "El gateway de pagos devuelve HTTP 502 en todas las transacciones."
uv run python -m src.adapters.inbound.cli triage --incident-id INC-1001 --raw-text -   # lee stdin
uv run python -m src.adapters.inbound.cli triage --file reporte.json                  # un único objeto
```

**HTTP (FastAPI):**

```bash
uv run uvicorn src.adapters.inbound.api.app:app --reload
```

```
POST /api/v1/incidents/triage
{"incident_id": "INC-1001", "raw_text": "..."}
```

Devuelve `200 OK` con `severity`, `component`, `recommended_team`, `rationale` y
`duplicate_group_key` (siempre `null` en el triaje stateless de H001; la clave
real la resuelve el alta persistente de H003). Las entradas inválidas responden
`422` con `application/problem+json` y un `code` estable.

Códigos de salida de la CLI: `0` éxito, `2` entrada inválida, `1` error
inesperado.

---

## 3. H002 · Resumen de incidentes activos

Expone el mismo caso de uso (`IncidentService.get_active_incidents_summary`) por
REST y CLI. El dominio calcula minutos de SLA, orden y totales; el adaptador
SQLite resuelve una sola consulta con `INNER JOIN sla_policies` e índice
`idx_incidents_component_status (component, status)`.

### Origen de datos

| `DATABASE_URL` | Resultado |
|---|---|
| ausente | Base SQLite en memoria, privada por repositorio |
| `sqlite:///:memory:` | Base SQLite en memoria |
| `sqlite:///ruta/incidentops.db` | Archivo relativo o absoluto |
| Otro esquema | Error de configuración; no se intenta abrir |

```powershell
$env:DATABASE_URL = "sqlite:///resumen-demo.db"
$env:PYTHONIOENCODING = "utf-8"
```

### CLI

```bash
uv run python -m src.adapters.inbound.cli summary
uv run python -m src.adapters.inbound.cli summary --component payments-gateway
uv run python -m src.adapters.inbound.cli summary --reference-time 2026-11-20T12:00:00
```

La salida es un JSON por `stdout`, idéntico al del canal HTTP:

```json
{
  "total_active": 2,
  "breached_count": 1,
  "incidents": [
    {
      "incident_id": "INC-2001",
      "title": "Pasarela de pagos caída",
      "component": "payments-gateway",
      "severity": "P0",
      "status": "OPEN",
      "elapsed_minutes": 61,
      "is_breached": true,
      "requires_escalation": false
    }
  ]
}
```

### HTTP

```bash
uv run uvicorn src.adapters.inbound.api.app:app --reload
```

```
GET /api/v1/incidents/summary
GET /api/v1/incidents/summary?component=payments-gateway
GET /api/v1/incidents/summary?reference_time=2026-11-20T12:00:00
```

`reference_time` es opcional y usa `YYYY-MM-DDTHH:MM:SS[.ffffff]`, con separador
`T` y sin zona horaria. Un componente sin coincidencias responde `200` con
totales en cero.

### Errores estables

| HTTP | CLI | `code` | Causa |
|---|---|---|---|
| 422 | 2 | `SUMMARY_SOLICITUD_INVALIDA` | Parámetro desconocido o repetido |
| 422 | 2 | `SUMMARY_COMPONENTE_DEMASIADO_LARGO` | `component` supera 128 caracteres |
| 422 | 2 | `SUMMARY_REFERENCIA_INVALIDA` | Fecha con zona, con espacio o no parseable |
| 409 | 1 | `SUMMARY_REFERENCIA_INCONSISTENTE` | Activo creado después del instante de referencia |
| 500 | 1 | `SUMMARY_ERROR_INTERNO` | Fallo inesperado sin detalles internos |

Los contratos viven en
[`specs/001-active-incidents-summary/contracts/`](specs/001-active-incidents-summary/contracts/)
y la guía de validación en
[`specs/001-active-incidents-summary/quickstart.md`](specs/001-active-incidents-summary/quickstart.md).

---

## 4. H003 · Ciclo de vida, duplicados y SLA

Registra un incidente de forma persistente, avisa en la misma respuesta si ya
existe un equivalente abierto y audita su SLA en cualquier instante de
referencia. Las tres reglas viven en `src/domain/`; los dos canales comparten
los DTOs de `src/adapters/inbound/lifecycle_contract.py` y serializan con
`model_dump(mode="json")`.

### CLI

```bash
uv run python -m src.adapters.inbound.cli create \
  --incident-id INC-3001 \
  --raw-text "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta." \
  --created-at 2026-11-20T10:00:00

uv run python -m src.adapters.inbound.cli sla \
  --incident-id INC-3001 --reference-time 2026-11-20T10:45:00
```

`create` responde con `severity`, `component`, `recommended_team`, `status`,
`created_at`, `resolved_at`, `duplicate_group_key`, `is_duplicate` y
`duplicate_of`; `sla` responde con `elapsed_minutes`, `allowed_minutes`,
`remaining_minutes`, `is_breached`, `requires_escalation` y `window`.

### HTTP

```
POST /api/v1/incidents                      → 201
GET  /api/v1/incidents/{incident_id}/sla    → 200
```

El alta acepta `created_at` opcional y responde `201` aunque haya duplicados.
La auditoría acepta `reference_time` opcional, responde `404` si el incidente no
existe y congela el cómputo en `resolved_at` cuando es terminal.

### Errores estables

| HTTP | CLI | `code` | Causa |
|---|---|---|---|
| 422 | 2 | `CREATE_*` | Identificador, texto, título o fecha inválidos |
| 422 | 2 | `CREATE_SOLICITUD_INVALIDA` | Campo o parámetro fuera del contrato |
| 409 | 1 | `CREATE_ID_CONFLICTO` | El identificador ya está almacenado (sin sobrescribir) |
| 422 | 2 | `SLA_REFERENCIA_INVALIDA` / `SLA_SOLICITUD_INVALIDA` | Fecha o parámetro inválidos |
| 422 | 1 | `SLA_REFERENCIA_INCONSISTENTE` | Referencia anterior a la creación |
| 409 | 1 | `SLA_DATOS_INCONSISTENTES` | Severidad, estado, equipo o fechas incoherentes |
| 404 | 1 | `SLA_INCIDENTE_NO_ENCONTRADO` | El incidente no existe |

Contratos y guía de validación:
[`specs/003-incident-lifecycle-sla/`](specs/003-incident-lifecycle-sla/).

---

## 5. Pruebas, fronteras y rendimiento

```bash
uv run pytest -v
uv run ruff check src/
```

La suite cubre H001, H002 y H003: escenarios BDD de cada especificación, fronteras
de SLA y de similitud en `tests/domain/`, alta, auditoría y duplicados en
`tests/application/test_services.py`, migración, conflicto e índice en
`tests/adapters/test_sqlite_repository.py`, y paridad HTTP/CLI en
`tests/test_spec_002_summary.py`, `tests/adapters/test_api.py`,
`tests/adapters/test_cli.py` y `tests/test_spec_003_lifecycle_sla.py`.

Benchmarks (no forman parte de `pytest` y no hacen aserciones de tiempo):

```bash
# Resumen filtrado sobre 10.000 activos, con plan de consulta,
# p95 del alta y de la auditoría, y plan de idx_incidents_dup_key
uv run python -m src.adapters.outbound.sqlite_repository --records 10000 --iterations 20

# Extremo a extremo por HTTP y CLI
uv run python tools/benchmark_summary.py --records 10000 --iterations 20
```

El motor histórico de triaje queda archivado en `legacy/triage_rules.py` como
evidencia: no se importa, no se modifica y no es fuente de verdad.

---

## 6. Governanza documental

- Constitución técnica: [`docs/constitution.md`](docs/constitution.md) y
  [`.specify/memory/constitution.md`](.specify/memory/constitution.md) (versión
  **1.1.0**).
- Hoja de ruta: [`docs/ROADMAP.md`](docs/ROADMAP.md).
- ADR: [`docs/adr/`](docs/adr/).
- Guía operativa para agentes: [`AGENTS.md`](AGENTS.md).
