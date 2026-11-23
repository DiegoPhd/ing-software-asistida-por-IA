# ROADMAP — IncidentOps

Hoja de ruta de producto y operaciones. Define **qué capacidad** entrega cada hito, no cómo se
implementa. El orden es intencional: cada hito habilita al siguiente.

---

## H001 · Triaje multi-interfaz

Clasificar y enrutar reportes de forma determinista y sin persistencia, con consumo inmediato
desde web y terminal.

- **Valor**: el reporte obtiene categoría y destino en el momento, sin depender de almacenamiento.
- **Listo cuando**: un mismo reporte produce la misma clasificación y enrutamiento en ambas interfaces.

## H002 · Resumen de incidentes activos — **Entregado (2026-11-22)**

Consultar los incidentes activos, los incumplimientos de SLA y el filtrado por componente desde
web y terminal.

- **Valor**: visibilidad operativa inmediata del estado del servicio.
- **Listo cuando**: ambas interfaces muestran el mismo resumen consistente para el mismo estado.
- **Entregado**: `GET /api/v1/incidents/summary` y `cli summary` comparten
  `IncidentService.get_active_incidents_summary` y el contrato
  `inbound/summary_contract.py`. El cálculo de SLA vive en
  `src/domain/sla_calculator.py`, la persistencia en
  `src/adapters/outbound/sqlite_repository.py` (una sola consulta e índice
  compuesto) y la composición en `src/adapters/outbound/factory.py`. Evidencia en
  [ADR-005](adr/005-resumen-activos-hexagonal.md).

### Deuda que habilitó H003 — **cerrada**

- `find_open_duplicates` entregaba solo candidatos activos del mismo componente; H003 añadió la
  similitud de texto y la ventana por severidad (P0 1 día, P1 2 días, P2 3 días, P3 4 días) en el
  dominio y resolvió `duplicate_group_key` con la clave del original más antiguo.
- Los días festivos locales siguen sin descontarse del cómputo hábil (ADR-002).

## H003 · Ciclo de vida, duplicados y SLA — **Entregado (2026-11-22)**

Registrar incidentes entrantes de forma persistente, alertar cuando ya existe otro equivalente
abierto y auditar su SLA en cualquier instante de referencia.

- **Valor**: trazabilidad del incidente, menos trabajo duplicado y SLA auditable a posteriori.
- **Listo cuando**: un incidente registrado conserva su historial, detecta duplicados abiertos y su
  estado de SLA puede reevaluarse en cualquier momento.
- **Entregado**: `POST /api/v1/incidents` y `cli create` comparten
  `IncidentService.create_incident` y `inbound/lifecycle_contract.py`; `GET
  /api/v1/incidents/{incident_id}/sla` y `cli sla` comparten
  `IncidentService.evaluate_incident_sla`. La equivalencia, la ventana por severidad y la ventana
  de cómputo viven en `src/domain/`; el reloj entra por `ClockPort`/`SystemClock` desde
  `factory.py`; la persistencia usa `INSERT` estricto, migración idempotente e
  `idx_incidents_dup_key`. Evidencia en [ADR-006](adr/006-ciclo-vida-duplicados-sla.md).

## H004 · Persistencia relacional dedicada y runtime en contenedores — **Entregado (2026-11-23)**

Preparar el servicio para ejecución reproducible en contenedores, con base de datos relacional
dedicada y verificación real de conectividad operativa.

- **Valor**: entorno reproducible y dependencia de datos explícita y verificable.
- **Listo cuando**: el servicio arranca en contenedor y confirma conectividad efectiva con su base
  de datos dedicada.
- **Entregado**: `GET /health` y `cli health` comparten `inbound/health_contract.py` y
  `IncidentService.check_health`; `src/adapters/outbound/postgres_repository.py` implementa el
  puerto completo con `psycopg`, DDL idempotente y `INSERT` estricto; `factory.py` selecciona
  SQLite o PostgreSQL por `DATABASE_URL` y distingue ausencia de vacío. El despliegue de referencia
  vive en `Dockerfile`, `docker-compose.yml`, `.dockerignore` y `.env.example`, y se verifica con
  `tools/verify_runtime.py --compose --resiliencia`. Evidencia en
  [ADR-004](adr/004-persistencia-postgresql-y-runtime-contenedores.md) y
  [ADR-008](adr/008-runtime-contenedores-docker-compose.md).
- **Deuda deliberada**: el bloqueo por componente sigue siendo de proceso; no hay migraciones
  versionadas ni pooler y los datos SQLite no se migran automáticamente.

---

## Criterios del roadmap

- Cada hito se cierra con su ADR en `docs/adr/` cuando implique una decisión arquitectónica.
- Rutas, contratos de interfaz, librerías y topología de despliegue se definen dentro de cada hito,
  no en este documento.
- Sin fechas ni estimaciones comprometidas: el orden refleja dependencias.
