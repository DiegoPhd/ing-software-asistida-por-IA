# Guía de Validación · Resumen de Incidentes Activos (H002)

**Fecha**: 2026-11-22 | **Contratos**: [API](./contracts/summary-api.md) · [CLI](./contracts/summary-cli.md) · [Esquema](./contracts/summary.schema.json)

Esta guía comprueba el hito de extremo a extremo sin levantar infraestructura externa. Todos los comandos se ejecutan desde la raíz del repositorio.

## 1 · Preparación

```bash
uv sync
uv run pytest -v
uv run ruff check src/
```

- La suite existente de H001 debe seguir en verde antes de empezar.
- `ruff` debe terminar sin errores con `TID251` y `TID252` activos.

## 2 · Base de datos de validación

Para que REST y CLI compartan datos, usa un archivo SQLite temporal:

**PowerShell**

```powershell
$env:DATABASE_URL = "sqlite:///resumen-demo.db"
$env:PYTHONIOENCODING = "utf-8"
```

**Bash**

```bash
export DATABASE_URL="sqlite:///resumen-demo.db"
export PYTHONIOENCODING="utf-8"
```

Siembra un conjunto reducido con el adaptador de salida (el registro HTTP pertenece a H003):

```bash
uv run python -c "from src.adapters.outbound.factory import create_repository; r=create_repository(); print(r.check_health())"
```

Inserta los incidentes con `save_incident` desde una sesión corta de Python, usando fechas naive. Para el ejemplo del contrato:

| `incident_id` | Componente | Severidad | Estado | `created_at` (para `reference_time=2026-11-20T12:00:00`) |
|---|---|---|---|---|
| `INC-2001` | `payments-gateway` | `P0` | `OPEN` | `2026-11-20T11:14:00` → 46 min, incumplido |
| `INC-2002` | `reporting-api` | `P2` | `IN_PROGRESS` | `2026-11-19T16:00:00` → 360 min hábiles (jueves 16-18 + viernes 08-12), escalamiento |
| `INC-2003` | `auth-identity` | `P1` | `RESOLVED` | fuera del resumen |

Elimina `resumen-demo.db` al terminar.

## 3 · Consulta HTTP

```bash
uv run uvicorn src.adapters.inbound.api.app:app --reload
```

```bash
curl "http://127.0.0.1:8000/api/v1/incidents/summary" -H "Accept: application/json"
curl "http://127.0.0.1:8000/api/v1/incidents/summary?component=payments-gateway"
curl "http://127.0.0.1:8000/api/v1/incidents/summary?reference_time=2026-11-20T12:00:00"
curl "http://127.0.0.1:8000/api/v1/incidents/summary?component=no-existe"
```

**Esperado**:

- `200` con `total_active`, `breached_count` e `incidents[]` conforme al esquema.
- El incidente `RESOLVED` no aparece.
- El filtro por componente reduce totales y detalle al subconjunto.
- El componente inexistente devuelve `200` con `{"total_active": 0, "breached_count": 0, "incidents": []}`.
- Una fecha con zona (`2026-11-20T12:00:00+00:00`) devuelve `422` con `SUMMARY_REFERENCIA_INVALIDA`.
- Un incidente activo creado después del instante de referencia devuelve `409` con `SUMMARY_REFERENCIA_INCONSISTENTE` y ningún total.

## 4 · Consulta CLI

```bash
uv run python -m src.adapters.inbound.cli summary
uv run python -m src.adapters.inbound.cli summary --component payments-gateway
uv run python -m src.adapters.inbound.cli summary --reference-time 2026-11-20T12:00:00
uv run python -m src.adapters.inbound.cli summary --reference-time "2026-11-20 12:00:00"
```

**Esperado**:

- Salida JSON por `stdout`, misma estructura y valores que la respuesta HTTP para el mismo instante.
- El resultado vacío sale con código `0` y `incidents` vacío.
- Fecha mal formada o con zona: código `2`, `stderr` con `SUMMARY_REFERENCIA_INVALIDA` y `stdout` vacío.
- `--component` de más de 128 caracteres: código `2` con `SUMMARY_COMPONENTE_DEMASIADO_LARGO`.

## 5 · Pruebas de la especificación

```bash
uv run pytest tests/test_spec_002_summary.py -v
uv run pytest tests/domain/test_sla_calculator.py -v
```

Cubre:

1. Resumen global que excluye `RESOLVED` y `CLOSED`.
2. Conteo de incumplidos coherente con las banderas del detalle.
3. Filtro por componente y resultado vacío.
4. Paridad JSON entre HTTP y CLI.
5. Fronteras de SLA (un minuto antes, en el límite y un minuto después) y fines de semana en P2/P3.
6. Escalamiento exacto al 75 %, desactivado al incumplir.
7. Incoherencia temporal y errores estables.
8. Cumplimiento estructural de `IncidentRepositoryPort` por `SQLiteIncidentRepository`.
9. Una sola consulta SQL por resumen (sin N+1) y uso del índice compuesto.

## 6 · Rendimiento

```bash
uv run python -m src.adapters.outbound.sqlite_repository --records 10000 --iterations 20
```

**Esperado**: siembra de 10.000 incidentes, resumen filtrado por componente en una sola consulta y tiempo medio dentro del objetivo de `SC-001` (< 1 s). El adaptador informa el plan de consulta; debe mencionar `idx_incidents_component_status` para el filtro por componente.

## 7 · Correspondencia con los criterios de éxito

| Criterio | Cómo se valida |
|---|---|
| SC-001 | Benchmark de 10.000 registros |
| SC-002 | Escenario global con estados mezclados |
| SC-003 | Comparación estricta HTTP/CLI con el mismo `reference_time` |
| SC-004 | `breached_count` igual al número de `is_breached` del detalle |
| SC-005 | Tabla de fronteras P0 y P2 en las pruebas de dominio |
| SC-006 | Filtro por componente en ambos canales |
| SC-007 | Componente sin coincidencias y base sin activos |
| SC-008 | Errores 422/409 y códigos de salida de la CLI |

## 8 · Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| Resumen vacío por HTTP y con datos por CLI | Cada `:memory:` es privado por conexión: usa `sqlite:///archivo.db` para compartir |
| `sqlite3.ProgrammingError` por hilo | El repositorio debe abrirse con `check_same_thread=False` y cerrojo; no crees conexiones por petición |
| Acentos corruptos en la consola Windows | Define `PYTHONIOENCODING=utf-8` |
| `TypeError` al comparar fechas | Se mezcló un instante con zona con fechas naive; usa ISO 8601 sin zona |
| `ruff` falla por imports relativos | Usa imports absolutos `from src...`; `TID252` prohíbe `from ..` |
