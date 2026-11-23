# Modelo de Datos · Runtime PostgreSQL en contenedores (H004)

**Fecha**: 2026-11-23 | **Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

H004 no añade entidades de negocio ni modifica `src/domain/`: reutiliza `Incident`, `SLARule` y la
política de SLA de H003. Lo nuevo es un **estado de salud** de transporte, un **contrato de
configuración** y un **esquema persistido equivalente** en PostgreSQL. Los documentos públicos se
fijan en [contracts/health.schema.json](./contracts/health.schema.json).

## 1 · Estado de salud (capa de entrada)

| Campo | Tipo | Valores | Regla |
|---|---|---|---|
| `status` | `Literal["ok", "error"]` | `ok`, `error` | `ok` si y solo si la comprobación devolvió `True` en ese instante |
| `database` | `Literal["connected", "unavailable"]` | `connected`, `unavailable` | Pareja fija con `status`: `ok` ↔ `connected`; `error` ↔ `unavailable` |

- La pareja se construye con `to_health_response(connected: bool)`; no se acepta una combinación
  cruzada.
- `HealthResponse` vive en `src/adapters/inbound/health_contract.py` y la comparten HTTP y CLI.
- No incluye motor, host, usuario, versión, latencia ni causa del fallo (RNF-008).
- No se persiste ni se cachea: se calcula en cada consulta.

## 2 · Contrato de configuración (`DATABASE_URL`)

| Entrada | Motor | Resultado |
|---|---|---|
| Variable ausente (`None`) | SQLite | `:memory:` |
| `sqlite:///:memory:` | SQLite | `:memory:` |
| `sqlite:///ruta/al/archivo.db` | SQLite | archivo indicado |
| `postgresql://usuario:clave@host:5432/base` | PostgreSQL | repositorio PostgreSQL con ese DSN |
| `""` o solo espacios | — | `ConfigurationError` (`CONFIG_DATABASE_URL_INVALIDA`) |
| `postgres://…` | — | `ConfigurationError`; alias no admitido |
| `sqlite://`, `sqlite:///` sin ruta | — | `ConfigurationError` |
| Cualquier otro esquema | — | `ConfigurationError` |

- La interpretación ocurre **solo** en `src/adapters/outbound/factory.py` (FR-007).
- Los mensajes citan como máximo el esquema; nunca el DSN completo ni credenciales.
- Una configuración inválida no abre conexión, no cae a memoria y no produce documento de salud en la
  CLI (sale 2 con `problem+json` en stderr).

## 3 · Puerto `IncidentRepositoryPort` (sin cambios de firma)

| Método | Semántica PostgreSQL |
|---|---|
| `save_incident(incident) -> None` | `INSERT` estricto de una sentencia; `UniqueViolation` → `IncidentAlreadyExistsError`; nunca actualiza la fila previa |
| `get_incident(incident_id) -> Incident \| None` | `SELECT` con columnas explícitas; `None` si no existe |
| `find_open_duplicates(incident) -> Sequence[Incident]` | Solo activos, mismo componente, distinto identificador; sin similitud, sin ventana y sin orden |
| `list_active_incidents(component_filter) -> Sequence[Incident]` | Activos con `INNER JOIN sla_policies`; dos variantes SQL (con y sin filtro) para no degradar el índice; sin SLA y sin orden |
| `check_health() -> bool` | `SELECT 1` con espera de conexión ≤ 2 s; `True` solo si hay fila; cualquier error de conexión, autenticación o tiempo → `False`; nunca lanza y nunca ejecuta DDL |

La validación de invariantes de escritura (`incident_id` y `component` no vacíos, severidad con
política, estado conocido, fechas naive, terminal con `resolved_at`, equipo del catálogo) se replica
en el adaptador PostgreSQL igual que en SQLite, sin importar el otro adaptador (ADR-007 §4).

## 4 · Esquema PostgreSQL

Ambas tablas se crean con DDL idempotente al componer el repositorio cuando la base responde y, si no
estaba disponible, en la primera operación de negocio.

### `sla_policies`

| Columna | Tipo | Restricción |
|---|---|---|
| `severity` | `TEXT` | `PRIMARY KEY` |
| `max_resolution_minutes` | `INTEGER` | `NOT NULL` |
| `operates_24x7` | `INTEGER` | `NOT NULL`; `1`/`0` como en SQLite |

- Siembra desde `SLA_POLICY_TABLE` con `INSERT ... ON CONFLICT (severity) DO UPDATE`. Es siembra, no
  ruta de alta (ver [research.md](./research.md) D5).

### `incidents`

| Columna | Tipo | Restricción |
|---|---|---|
| `incident_id` | `TEXT` | `PRIMARY KEY` |
| `title` | `TEXT` | `NOT NULL` |
| `component` | `TEXT` | `NOT NULL` |
| `severity` | `TEXT` | `NOT NULL` |
| `status` | `TEXT` | `NOT NULL` |
| `created_at` | `TEXT` | `NOT NULL`; ISO 8601 naive con microsegundos |
| `resolved_at` | `TEXT` | `NULL` o ISO 8601 naive con microsegundos |
| `raw_text` | `TEXT` | `NULL` |
| `recommended_team` | `TEXT` | `NULL` |
| `duplicate_group_key` | `TEXT` | `NULL` |

### Índices

| Índice | Columnas | Uso |
|---|---|---|
| `idx_incidents_component_status` | `(component, status)` | Resumen filtrado y candidatos a duplicado |
| `idx_incidents_dup_key` | `(duplicate_group_key, status)` | Consulta por grupo de duplicados |

- No hay claves foráneas: SQLite tampoco las declara y el `INNER JOIN` con `sla_policies` es
  semántico, no referencial.
- No hay columnas nuevas de H004; el esquema replica H003.
- No hay migraciones versionadas ni `ALTER TABLE` automático: el hito asume una base PostgreSQL nueva
  y la spec excluye migrar datos de SQLite.

## 5 · Formato temporal persistido

- `created_at` y `resolved_at` se escriben como
  `YYYY-MM-DDTHH:MM:SS.ffffff` (`isoformat(timespec="microseconds")`) en ambos motores.
- Se leen con `datetime.fromisoformat`; las fechas son naive y se rechaza cualquier valor con zona.
- No se usan `TIMESTAMP`, `TIMESTAMPTZ`, épocas numéricas, `now()` del motor ni conversiones de zona.
- El orden lexicográfico del texto coincide con el cronológico, por lo que ningún adaptador necesita
  ordenar ni convertir para comparar.
- Valores históricos de SQLite sin microsegundos siguen siendo legibles; el normalizador solo aplica
  a nuevas escrituras.

## 6 · Ciclo de vida del esquema y de la salud

```text
[composición] --base responde--> esquema asegurado (ready)
       |
       +--base no responde--> servicio arriba, esquema pendiente
                                   |
                     /health --> 503 (solo SELECT 1; nunca DDL)
                                   |
                     operación de negocio --> reintenta DDL bajo cerrojo
                                   |
                     base vuelve --> DDL idempotente OK --> operación continúa
                                   |
                     /health --> 200 sin reiniciar API (≤ 5 s)
```

- `check_health` **no** crea tablas, no siembra políticas y no exige que existan: informa
  conectividad real, tal como fija la clarificación de la spec.
- Un fallo de DDL durante una operación de negocio se propaga como error inesperado genérico (500 en
  HTTP, salida 1 en CLI), sin códigos nuevos y sin filtrar el DSN.
- El cerrojo de inicialización es de proceso y protege solo el DDL; las conexiones por operación no se
  comparten entre hilos.

## 7 · Invariantes que H004 no altera

- Severidades y ventanas: P0 60 min 24x7, P1 240 min 24x7, P2 480 min L-V 08:00-18:00, P3 1440 min
  L-V 08:00-18:00; escalamiento al 75 %; incumplimiento estricto `elapsed > allowed`.
- Estados: `OPEN`, `IN_PROGRESS`, `RESOLVED`, `CLOSED`; terminales con `resolved_at`.
- Duplicados: activos, mismo componente, distinto id, texto no vacío, similitud ≥ 0.75 y ventana por
  severidad del más antiguo, todo en `src/domain/triage_rules.py`.
- Festivos locales siguen sin descontarse (deuda de ADR-002).
- Una sola réplica de API y cerrojo por componente de proceso (ADR-006/ADR-007).
