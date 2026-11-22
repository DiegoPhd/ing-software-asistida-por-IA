# IncidentOps — Proyecto Semilla (Semana 1)

**IncidentOps** es un sistema backend en Python gestionado con [`uv`](https://docs.astral.sh/uv/) que administra reportes de incidentes de software, evalúa acuerdos de nivel de servicio (**SLA**) sobre SQLite y ejecuta reglas de **triaje y enrutamiento de tickets**.

Este repositorio sirve como banco de pruebas práctico para la **Semana 1** de *Ingeniería de Software Asistida por Inteligencia Artificial (ISIA)* bajo un enfoque **100% *AI for Software Engineering***.

---

## Requisitos e Instalación con `uv`

- **Python 3.10+** y **[`uv`](https://docs.astral.sh/uv/)**.
- Dependencias declaradas en [`pyproject.toml`](pyproject.toml):
  - `tiktoken`: Para medir con precisión matemática el consumo de tokens BPE (`o200k_base` / `cl100k_base`) en las distintas estrategias de recolección de contexto.

Para inicializar el entorno virtual e instalar las dependencias:

```bash
uv sync
```

---

## Comandos Principales para la Práctica

Ejecuta todos los comandos desde la raíz del repositorio usando `uv run`:

### 1. Fase 1 — Auditoría de Tokens con `tiktoken`: Fuerza Bruta vs. `grep` vs. LSP
Compara cuántos tokens reales consume leer todos los archivos del repositorio (`glob` + `read`), leer los archivos `.py` coincidentes (`grep` + `read`) o extraer únicamente la definición, firmas de tipos y referencias de un símbolo como lo hace un servidor **LSP**:

```bash
uv run python -m src.context_audit --symbol evaluate_sla_status
uv run python -m src.context_audit --symbol get_active_incidents_summary
uv run python -m src.context_audit --symbol classify_incident_report
```

Para comparar el impacto en tokens de distintos formatos de serialización de datos (JSON indentado, JSON compacto, YAML, CSV):

```bash
uv run python -m src.context_audit --compare-formats
```

### 2. Fase 2 — Benchmark del Repositorio de Incidentes (10,000 registros)
Ejecuta el escenario con deuda técnica (escaneo completo en memoria y problema de consultas N+1 sobre 10,000 incidentes en SQLite):

```bash
uv run python -m src.incident_repository
```

### 3. Hito 001 — Triaje por HTTP y CLI
El motor de triaje vive en `src/domain/triage.py` y se expone a través de un único caso de uso (`IncidentService.triage_incident`) consumido por dos adaptadores. La operación es stateless: no lee ni escribe base de datos.

**CLI (Typer):**

```bash
uv run python -m src.adapters.inbound.cli triage --incident-id INC-1001 --raw-text "El gateway de pagos devuelve HTTP 502 en todas las transacciones."
uv run python -m src.adapters.inbound.cli triage --incident-id INC-1001 --raw-text -   # lee stdin
uv run python -m src.adapters.inbound.cli triage --file reporte.json                  # un único objeto
```

La salida es un JSON idéntico al de HTTP. Códigos de salida: `0` éxito, `2` entrada inválida, `1` error inesperado.

**HTTP (FastAPI):**

```bash
uv run uvicorn src.adapters.inbound.api.app:app --reload
```

```
POST /api/v1/incidents/triage
{"incident_id": "INC-1001", "raw_text": "..."}
```

Devuelve `200 OK` con `severity`, `component`, `recommended_team`, `rationale` y `duplicate_group_key` (siempre `null` en H001). Las entradas vacías o con solo espacios responden `422` con `application/problem+json` y un `code` estable.

La especificación completa está en [`docs/specs/h001-triaje-multi-interfaz.md`](docs/specs/h001-triaje-multi-interfaz.md) y las decisiones de frontera en [`docs/adr/004-contrato-interfaces-h001.md`](docs/adr/004-contrato-interfaces-h001.md).

**Pruebas:**

```bash
uv run pytest
```

El motor anterior queda archivado en `legacy/triage_rules.py` como evidencia histórica: no es invocable ni fuente de verdad.

### 4. Verificación del Cálculo Determinista de SLA (`src/sla_calculator.py`)
Ejecuta la demostración del cálculo de SLA actual (donde se evidencia el bug de horario hábil en tickets `P2`/`P3`):

```bash
uv run python -m src.sla_calculator
```
