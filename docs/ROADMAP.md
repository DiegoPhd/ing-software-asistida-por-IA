# ROADMAP — IncidentOps

Hoja de ruta de producto y operaciones. Define **qué capacidad** entrega cada hito, no cómo se
implementa. El orden es intencional: cada hito habilita al siguiente.

---

## H001 · Triaje multi-interfaz

Clasificar y enrutar reportes de forma determinista y sin persistencia, con consumo inmediato
desde web y terminal.

- **Valor**: el reporte obtiene categoría y destino en el momento, sin depender de almacenamiento.
- **Listo cuando**: un mismo reporte produce la misma clasificación y enrutamiento en ambas interfaces.

## H002 · Resumen de incidentes activos

Consultar los incidentes activos, los incumplimientos de SLA y el filtrado por componente desde
web y terminal.

- **Valor**: visibilidad operativa inmediata del estado del servicio.
- **Listo cuando**: ambas interfaces muestran el mismo resumen consistente para el mismo estado.

## H003 · Ciclo de vida, duplicados y SLA

Registrar incidentes entrantes de forma persistente, alertar cuando ya existe otro equivalente
abierto y auditar su SLA en cualquier instante de referencia.

- **Valor**: trazabilidad del incidente, menos trabajo duplicado y SLA auditable a posteriori.
- **Listo cuando**: un incidente registrado conserva su historial, detecta duplicados abiertos y su
  estado de SLA puede reevaluarse en cualquier momento.

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
