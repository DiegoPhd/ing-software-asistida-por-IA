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

### Deuda pendiente que habilita H003

- `find_open_duplicates` solo entrega candidatos activos del mismo componente:
  falta la similitud de texto y la ventana por severidad (P0 1 día, P1 2 días,
  P2 3 días, P3 4 días) y el `duplicate_group_key` sigue en `null`.
- Los días festivos locales siguen sin descontarse del cómputo hábil (ADR-002).

## H003 · Ciclo de vida, duplicados y SLA

Registrar incidentes entrantes de forma persistente, alertar cuando ya existe otro equivalente
abierto y auditar su SLA en cualquier instante de referencia.

- **Valor**: trazabilidad del incidente, menos trabajo duplicado y SLA auditable a posteriori.
- **Listo cuando**: un incidente registrado conserva su historial, detecta duplicados abiertos y su
  estado de SLA puede reevaluarse en cualquier momento.
- **Habilitado por H002**: el puerto `IncidentRepositoryPort` ya expone
  `save_incident`, `get_incident` y `find_open_duplicates`; la calibración de
  similitud y la ventana por severidad es la deuda pendiente de este hito.

## H004 · Persistencia relacional dedicada y runtime en contenedores

Preparar el servicio para ejecución reproducible en contenedores, con base de datos relacional
dedicada y verificación real de conectividad operativa.

- **Valor**: entorno reproducible y dependencia de datos explícita y verificable.
- **Listo cuando**: el servicio arranca en contenedor y confirma conectividad efectiva con su base
  de datos dedicada.

---

## Criterios del roadmap

- Cada hito se cierra con su ADR en `docs/adr/` cuando implique una decisión arquitectónica.
- Rutas, contratos de interfaz, librerías y topología de despliegue se definen dentro de cada hito,
  no en este documento.
- Sin fechas ni estimaciones comprometidas: el orden refleja dependencias.
