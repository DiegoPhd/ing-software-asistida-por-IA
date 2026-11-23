# Guía de Validación · Ciclo de vida, duplicados y SLA (H003)

**Fecha**: 2026-11-22 | **Contratos**: [Alta](./contracts/create-api.md) ·
[SLA](./contracts/sla-api.md) · [CLI](./contracts/lifecycle-cli.md) ·
[Esquema de alta](./contracts/incident-created.schema.json) ·
[Esquema de SLA](./contracts/sla-evaluation.schema.json)

Esta guía comprueba el hito de extremo a extremo sin infraestructura externa. Todos los comandos se
ejecutan desde la raíz del repositorio.

## 1 · Preparación

```bash
uv sync
uv run pytest -v
uv run ruff check src/
```

- H001 y H002 deben seguir en verde antes de empezar; H003 no cambia sus valores.
- `ruff` debe terminar sin errores con `TID251` y `TID252` activos.

## 2 · Almacenamiento de validación

Para que REST y CLI compartan datos, usa un archivo SQLite temporal y elimínalo al terminar:

**PowerShell**

```powershell
$env:DATABASE_URL = "sqlite:///ciclo-vida-demo.db"
$env:PYTHONIOENCODING = "utf-8"
Remove-Item ciclo-vida-demo.db -ErrorAction SilentlyContinue
```

**Bash**

```bash
export DATABASE_URL="sqlite:///ciclo-vida-demo.db"
export PYTHONIOENCODING="utf-8"
rm -f ciclo-vida-demo.db
```

La primera operación crea el esquema, migra las columnas nuevas y crea
`idx_incidents_component_status` e `idx_incidents_dup_key`.

## 3 · Alta por consola

```bash
uv run python -m src.adapters.inbound.cli create \
  --incident-id INC-3001 \
  --raw-text "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta." \
  --created-at 2026-11-20T10:00:00
```

**Esperado**: salida `0`, documento JSON con `severity: "P0"`, `component: "payments-gateway"`,
`recommended_team: "Backend-Core"`, `status: "OPEN"`, `created_at: "2026-11-20T10:00:00"`,
`is_duplicate: false`, `duplicate_of: []` y `duplicate_group_key: null`.

```bash
# Segundo reporte equivalente del mismo componente, dentro de la ventana de P0
uv run python -m src.adapters.inbound.cli create \
  --incident-id INC-3002 \
  --raw-text "La pasarela de pagos está caída: ningún comercio puede cobrar con tarjeta." \
  --created-at 2026-11-20T10:05:00
```

**Esperado**: salida `0`, `201` equivalente en HTTP, `is_duplicate: true`,
`duplicate_of: ["INC-3001"]` y `duplicate_group_key: "INC-3001"`; `INC-3001` queda intacto.

```bash
# Mismo identificador: conflicto, sin sobrescritura
uv run python -m src.adapters.inbound.cli create \
  --incident-id INC-3001 --raw-text "Otro texto" --created-at 2026-11-20T11:00:00
```

**Esperado**: salida `1`, `stderr` con `CREATE_ID_CONFLICTO`, sin JSON en `stdout`, y `INC-3001` con
su texto, estado y clave anteriores.

## 4 · Auditoría de SLA por consola

```bash
uv run python -m src.adapters.inbound.cli sla \
  --incident-id INC-3001 --reference-time 2026-11-20T10:45:00
```

**Esperado**: `elapsed_minutes: 45`, `allowed_minutes: 60`, `remaining_minutes: 15`,
`is_breached: false`, `requires_escalation: true` (umbral exacto del 75 %), `window: "24x7"`.

```bash
uv run python -m src.adapters.inbound.cli sla \
  --incident-id INC-3001 --reference-time 2026-11-20T11:01:00
```

**Esperado**: `elapsed_minutes: 61`, `is_breached: true`, `requires_escalation: false`,
`remaining_minutes: -1`.

```bash
# Referencia anterior a la creación: 422 en HTTP, salida 1 en CLI
uv run python -m src.adapters.inbound.cli sla \
  --incident-id INC-3001 --reference-time 2026-11-20T09:59:59

# Incidente inexistente: 404 en HTTP, salida 1 en CLI
uv run python -m src.adapters.inbound.cli sla --incident-id INC-9999

# Fecha con zona horaria: 422 en HTTP, salida 2 en CLI
uv run python -m src.adapters.inbound.cli sla \
  --incident-id INC-3001 --reference-time 2026-11-20T10:00:00+00:00
```

## 5 · Alta y auditoría por HTTP

```bash
uv run uvicorn src.adapters.inbound.api.app:app --reload
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/incidents \
  -H "Content-Type: application/json" \
  -d '{"incident_id":"INC-3101","raw_text":"La base de datos PostgreSQL está lenta, consultas de 12 segundos.","created_at":"2026-11-06T17:00:00"}'

curl "http://127.0.0.1:8000/api/v1/incidents/INC-3101/sla?reference_time=2026-11-09T09:00:00"
```

**Esperado**:

- Alta `201` con `severity: "P2"`, `component: "database-cluster"`, `recommended_team: "Data-DBA"`.
- SLA con `elapsed_minutes: 120`, `allowed_minutes: 480`, `remaining_minutes: 360`,
  `is_breached: false`, `requires_escalation: false`, `window: "BUSINESS_HOURS"`: el fin de semana y
  las horas fuera de ventana no acumulan.
- Un campo desconocido en el cuerpo del alta devuelve `422 CREATE_SOLICITUD_INVALIDA`.
- Un parámetro desconocido o repetido en la auditoría devuelve `422 SLA_SOLICITUD_INVALIDA`.

## 6 · Persistencia y reinicio

1. Registra un incidente con `create`.
2. Detén y vuelve a arrancar el proceso (o la terminal) manteniendo `DATABASE_URL` al mismo archivo.
3. Consulta `sla` y `summary` para ese incidente.

**Esperado**: el incidente sigue disponible con el mismo identificador, título, componente,
severidad, estado, `created_at`, `recommended_team` y `duplicate_group_key`; aparece en el resumen de
activos sin duplicarse.

## 7 · Pruebas de la especificación

```bash
uv run pytest tests/test_spec_003_lifecycle_sla.py -v
uv run pytest tests/domain/test_duplicate_rules.py tests/domain/test_sla_calculator.py -v
uv run pytest tests/application/test_services.py tests/adapters/test_sqlite_repository.py -v
```

Cubren:

1. Alta persistente y recuperación tras reinicio.
2. Aviso de duplicados con `duplicate_of` ordenado, herencia de clave y ausencia de falsos positivos
   (terminal, otro componente, similitud por debajo del umbral, fuera de ventana, sin texto).
3. Auditoría de SLA activa, en terminales congelados y en las fronteras de la política.
4. Paridad HTTP/CLI por igualdad estricta de documentos y códigos de error equivalentes.
5. Fronteras de similitud y ventana, concurrencia con dos hilos y volumen de 10.000 activos.

## 8 · Rendimiento e índice

```bash
uv run python -m src.adapters.outbound.sqlite_repository --records 10000 --iterations 20
```

**Esperado**: siembra de 10.000 activos y resumen dentro del objetivo de H002. Para el índice nuevo,
comprueba el plan de consulta por `duplicate_group_key` y `status` (`EXPLAIN QUERY PLAN` debe
mencionar `idx_incidents_dup_key`) y registra el tiempo del alta y de la auditoría con 10.000 activos
como evidencia de `SC-006`.

## 9 · Correspondencia con los criterios de éxito

| Criterio | Cómo se valida |
|---|---|
| SC-001 | Alta, reinicio del proceso y consulta posterior sobre el mismo archivo |
| SC-002 | Escenarios de duplicado y de falsos positivos |
| SC-003 | Comparación estricta HTTP/CLI del documento de SLA |
| SC-004 | Comparación estricta de `is_duplicate`, `duplicate_of` y `duplicate_group_key` |
| SC-005 | Fronteras P0 60/61, P1 180 y P2 viernes→lunes |
| SC-006 | Medición con 10.000 activos |
| SC-007 | 404, 422 y entradas inválidas sin documentos parciales |
| SC-008 | Verificación de que el incidente previo no cambia tras un aviso |
| SC-009 | Presencia del registrado en `summary` |
| SC-010 | Prueba de dos altas concurrentes con barrera |

## 10 · Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `404` en la auditoría por HTTP y el incidente existe por CLI | Cada `:memory:` es privado: usa `sqlite:///archivo.db` para compartir |
| `409 CREATE_ID_CONFLICTO` al repetir un escenario | El archivo conserva datos: elimínalo o usa identificadores nuevos |
| `TypeError` al comparar fechas | Se mezcló un instante con zona; usa ISO 8601 sin zona |
| Fechas distintas entre HTTP y CLI | La CLI debe serializar con `model_dump(mode="json")` |
| Acentos corruptos en la consola Windows | Define `PYTHONIOENCODING=utf-8` |
| El segundo alta de un escenario concurrente no avisa | Comprueba que ambos hilos usan la misma instancia de `IncidentService` y el mismo componente |
