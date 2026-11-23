# Constitución de IncidentOps

- **Estado**: Vigente
- **Versión**: 1.1.0
- **Fecha**: 2026-11-22
- **Última enmienda**: 2026-11-22
- **Ámbito**: todo el repositorio
- **Precedencia**: Constitución → ADR → código. `AGENTS.md` es guía operativa,
  `ROADMAP.md` define capacidades y `CONTEXT_LOG.md` es bitácora; ninguno puede
  contradecir esta Constitución.
- **Enmienda**: PR + ADR. Si un ADR entra en conflicto, primero se enmienda la
  Constitución.

---

## 1. Dominio determinista único

### 1.1 Fuente única de verdad

`src/domain/` es la única definición de entidades, objetos de valor y reglas de
negocio: `Incident`, `SLARule`, `SLAEvaluation`, `TriageResult`, `SeverityLevel`,
`IncidentStatus`, `Team`, cálculo de SLA, triaje y duplicados.

- Prohibido redeclarar esos tipos o sus reglas en `application`, `adapters`, DTOs,
  esquemas Pydantic, SQL o CLI. Los DTOs de transporte se mapean explícitamente en
  el borde.
- El dominio es puro: sin `sqlite3`, `json`, `argparse`, `fastapi`, `typer`,
  `print`/logging, red, sistema de archivos, `datetime.now()` ni `random`.
- El tiempo de referencia entra como argumento o mediante `ClockPort`. Misma
  entrada + mismo historial + mismo `reference_time` ⇒ misma salida.
- Sin estado global mutable ni efectos observables fuera del valor de retorno.

### 1.2 Severidades y SLA

| Severidad | Minutos permitidos | Ventana | Escalamiento (75 %) |
|-----------|-------------------:|---------|--------------------:|
| P0        | 60                 | 24x7    | 45                  |
| P1        | 240                | 24x7    | 180                 |
| P2        | 480                | L-V 08:00-18:00 | 360        |
| P3        | 1440               | L-V 08:00-18:00 | 1080       |

- P2 y P3 solo acumulan minutos dentro de la ventana hábil de lunes a viernes,
  08:00-18:00. Sábados, domingos y horas fuera de ventana no acumulan.
- Los días festivos no se contabilizan todavía: es deuda explícita (`TODO`) y
  exige un ADR y un puerto de calendario antes de implementarse.
- `elapsed_minutes` se trunca a minutos enteros.
- Incumplimiento estricto: `elapsed_minutes > allowed_minutes`. En el límite exacto
  no hay incumplimiento.
- Escalamiento: `status` activo, sin incumplimiento y
  `elapsed_minutes >= int(allowed_minutes * 0.75)`.
- `end_time = resolved_at or reference_time`. Si `reference_time < created_at`, es
  un error de dominio.
- Las fechas son naive consistentes; no se mezclan `datetime` aware y naive.

### 1.3 Estados del incidente

Estados canónicos: `OPEN`, `IN_PROGRESS`, `RESOLVED`, `CLOSED`.

- Activos: `OPEN`, `IN_PROGRESS`; son los únicos que aparecen en el resumen de
  activos.
- Terminales: `RESOLVED`, `CLOSED`; detienen el reloj de SLA y no escalan.
- `RESOLVED` y `CLOSED` exigen `resolved_at`.
- `INVESTIGATING` queda fuera del modelo; `IN_PROGRESS` es el único estado de
  trabajo en curso.

### 1.4 Triaje

El triaje se basa en impacto real, nunca en palabras emocionales como "urgente" o
"hoy". La precedencia es P0 → P1 → P2 → P3; si ninguna regla aplica, el valor por
defecto es P2.

| Severidad | Criterio de impacto |
|-----------|---------------------|
| P0 | Indisponibilidad total/global/multi-tenant, pagos caídos, fuga de datos entre organizaciones |
| P1 | Saturación o timeouts de conexiones/pool, degradación severa del servicio |
| P2 | Lentitud medible, cuenta bloqueada, degradación acotada |
| P3 | Cosmética, staging, sin impacto operativo |

La tabla exhaustiva de palabras y componentes es responsabilidad exclusiva de
`src/domain/`; cambiarla exige pruebas de aceptación. Ninguna capa externa puede
reimplementarla.

**Lote y original:** el lote se procesa en orden ascendente de `created_at`; ante
empate, por `incident_id` ascendente. El primero es el original.

**Duplicados:** similitud `SequenceMatcher` sobre texto en minúsculas ≥ 0.75,
dentro de la ventana de la severidad: P0 1 día, P1 2 días, P2 3 días, P3 4 días.
Solo cuentan candidatos con `0 <= created_at - prev_created_at <= ventana`.
`duplicate_group_key` es siempre el `incident_id` del original más antiguo, nunca
el de otro duplicado; si el candidato ya es duplicado, se hereda su clave.

### 1.5 Equipos válidos

El catálogo de equipos es cerrado y vive en el dominio. Añadir o retirar un equipo
exige ADR y pruebas de aceptación.

| Componente | Equipo |
|------------|--------|
| `payments-gateway` | `Backend-Core` |
| `auth-identity` | `Security-IAM` |
| `database-cluster` | `Data-DBA` |
| `infra-certificates` | `Platform-SRE` |
| `security-audit` | `Security-IAM` |
| `reporting-api` | `otros` |

`otros` es el único valor de reserva; no es un equipo con guardia ni una vía para
evadir el catálogo.

---

## 2. Arquitectura Hexagonal (ADR-003)

### 2.1 Capas y regla de dependencia

| Ruta | Responsabilidad |
|------|-----------------|
| `src/domain/` | Entidades, valores y reglas puras |
| `src/application/` | `IncidentService`, casos de uso, puertos y transacciones |
| `src/adapters/inbound/` | REST, CLI y futuro MCP |
| `src/adapters/outbound/` | SQLite, PostgreSQL futuro, JSON de muestra |
| Raíz de composición (`src/adapters/outbound/factory.py`) | Único lugar que conoce clases concretas, selecciona el repositorio por `DATABASE_URL` e inyecta adaptadores |

La dependencia es unidireccional: `adapters → application → domain`. El dominio no
importa nada de `src`; la aplicación no importa frameworks ni adaptadores
concretos.

### 2.2 Puertos

- Los puertos secundarios se declaran con `typing.Protocol`, sin herencia
  obligatoria. En H002 el puerto vigente es `IncidentRepositoryPort`;
  `SlaPolicyPort` y `ClockPort` se incorporarán cuando un caso de uso los
  requiera, con implementación y prueba reales.
- Los puertos de entrada son los casos de uso que expone `IncidentService`. En
  H002: triaje individual y resumen de activos. Triaje por lote, registro y
  reevaluación de SLA quedan en el ROADMAP y se añadirán cuando su hito los
  requiera.
- `IncidentService` solo secuencia, transacciona y traduce entre puertos; no
  contiene reglas de negocio, SQL ni detalles de transporte.

### 2.3 Adaptadores

- **Entrada:** REST con FastAPI + Pydantic v2 y CLI con Typer. Ambos validan,
  traducen y formatean; no clasifican ni calculan SLA.
- **MCP futuro:** será un adaptador de entrada sobre los mismos casos de uso. No
  puede duplicar lógica ni obligar a cambiar el dominio; si necesita una capacidad
  nueva, se añade un caso de uso.
- **Salida:** SQLite con `sqlite3` estándar, PostgreSQL en H004 y lectura del JSON
  de muestra. Todo el SQL, DDL, siembra de políticas y mapeo desde filas vive
  exclusivamente aquí.
- La deuda deliberada de `get_active_incidents_summary` (`SELECT *`, filtrado en
  Python y N+1) queda confinada al adaptador SQLite hasta el refactor de Fase 2; no
  se replica en otros adaptadores ni se traslada al dominio.

### 2.4 Migración desde el código actual

`src/models.py`, `legacy/triage_rules.py`, `src/sla_calculator.py` y
`src/incident_repository.py` son legado transitorio. No se añaden reglas nuevas
allí. Cada reto migra su capacidad al layout hexagonal y retira o reemplaza el
punto de entrada anterior en el mismo PR, para no dejar dos formas competidoras de
invocar el sistema. `AGENTS.md` y `README.md` se actualizan en ese mismo cambio.

---

## 3. Gobernanza técnica y calidad

### 3.1 Stack

- Python >= 3.10 gestionado con `uv`; `[tool.uv] package = false` e imports
  absolutos resueltos desde la raíz del repositorio.
- REST: FastAPI + Pydantic v2. CLI: Typer.
- Persistencia: `sqlite3` de la biblioteca estándar, sin ORMs pesados.
- Cualquier cambio de motor de base de datos exige su propio ADR previo (H004:
  PostgreSQL dedicado).
- La biblioteca estándar es la opción por defecto; una dependencia nueva debe
  justificarse en el PR.

### 3.2 BDD y pruebas

- Cada capacidad se especifica en español con `Given / When / Then`.
- Las pruebas de aceptación se automatizan con `pytest` y se ejecutan con
  `uv run pytest`.
- Las pruebas de aceptación atraviesan el adaptador de entrada o el caso de uso con
  dobles en memoria de los puertos; las reglas de dominio tienen pruebas unitarias
  table-driven.
- Tiempo fijo e inyectado; sin `sleep`, red ni base de datos real en pruebas de
  dominio.
- Como hoy no existe suite, el primer PR que toque una capacidad crea el arnés y no
  se considera terminado sin sus pruebas ejecutadas.

### 3.3 Puertas de calidad

Un PR no se integra si incumple cualquiera de estas condiciones:

1. El dominio no importa frameworks, persistencia, CLI ni relojes implícitos.
2. No hay tipos ni reglas de negocio duplicados fuera de `src/domain/`.
3. REST, CLI y el futuro MCP comparten el mismo caso de uso.
4. Las pruebas de aceptación y unitarias pasan.
5. Toda decisión estructural tiene ADR en `docs/adr/` con diagrama Mermaid cuando
   aclare fronteras.
6. La documentación afectada (`AGENTS.md`, `README.md`) se actualiza en el mismo
   PR.
7. Código, docstrings y documentación se mantienen en español; `CONTEXT_LOG.md` no
   se reescribe como relleno.

### 3.4 Fuera de alcance

Esta Constitución no fija comandos, tareas archivo por archivo ni fechas. Eso
corresponde a `AGENTS.md`, `README.md` y `ROADMAP.md`.
