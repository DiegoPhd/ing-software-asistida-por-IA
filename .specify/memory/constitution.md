# Constitución de IncidentOps

- **Estado**: Vigente
- **Ámbito**: todo el repositorio `IncidentOps` (dominio, aplicación, adaptadores,
  documentación y pruebas)
- **Precedencia**: Constitución → ADR → código. `AGENTS.md` es guía operativa,
  `ROADMAP.md` define capacidades y `CONTEXT_LOG.md` es bitácora; ninguno puede
  contradecir esta Constitución.

## Principios Fundamentales

### I. Núcleo determinista único

`src/domain/` es la única definición de entidades, objetos de valor y reglas de
negocio de IncidentOps, y se organiza en tres módulos canónicos:

- `models.py`: `Incident`, `SLARule`, `SLAEvaluation`, `SeverityLevel`,
  `IncidentStatus` y `Team`.
- `triage_rules.py`: clasificación por impacto, catálogo de componentes/equipos y
  detección de duplicados.
- `sla_calculator.py`: política y cálculo de SLA.

Ninguna otra capa DEBE redeclarar esos tipos ni sus reglas. DTOs de transporte,
esquemas Pydantic, filas SQL y modelos de CLI se mapean explícitamente en el borde
y SÓLO PUEDEN contener lo necesario para el transporte.

Mientras dure la migración, `src/models.py`, `legacy/triage_rules.py` y
`src/sla_calculator.py` son legado transitorio: NO DEBEN recibir reglas nuevas ni
convertirse en fuente de verdad alternativa. Cada reto migra su capacidad a
`src/domain/` y retira el punto de entrada anterior en el mismo PR.

**Razón**: una sola definición elimina la divergencia histórica entre
`models.py` y `sla_calculator.py` y garantiza que REST, CLI, MCP y persistencia
evalúen exactamente las mismas reglas.

### II. Dominio puro y auditable

`src/domain/` NO DEBE importar nada fuera de la biblioteca estándar de Python ni
módulos de `src` ajenos a `src.domain`. En particular, están prohibidos `sqlite3`,
`psycopg`, `psycopg2`, `json`, `argparse`, `os.environ`, `fastapi`, `typer`,
`pydantic`, ORMs, `print`, logging, red, sistema de archivos, `datetime.now()` y
`random`.

El tiempo de referencia DEBE entrar como argumento explícito o mediante
`ClockPort`. El dominio NO DEBE mantener estado global mutable ni producir efectos
observables fuera de su valor de retorno. Misma entrada, mismo historial y mismo
`reference_time` DEBEN producir la misma salida, byte a byte en los valores
devueltos.

**Razón**: sin reloj, entorno ni E/S implícitos, las reglas son reproducibles y
verificables con pruebas unitarias sin infraestructura.

### III. Arquitectura Hexagonal estricta

La dependencia es unidireccional y no negociable:
`src/adapters/ → src/application/ → src/domain/`.

| Ruta | Responsabilidad |
|------|-----------------|
| `src/domain/` | Entidades, valores y reglas puras |
| `src/application/` | Casos de uso, puertos y transacciones |
| `src/adapters/inbound/` | REST (FastAPI), CLI (Typer) y futuro MCP |
| `src/adapters/outbound/` | Persistencia y fuentes de datos; intercambiables |
| `src/adapters/outbound/factory.py` | Único punto que construye clases concretas y selecciona el repositorio por `DATABASE_URL` |

Reglas obligatorias:

- `src/application/` NO DEBE importar frameworks web, `sqlite3`, `psycopg`,
  `psycopg2`, SQL ni módulos de `src.adapters`.
- `src/adapters/` NO DEBE importar otro adaptador concreto para reutilizar lógica;
  comparte casos de uso, no implementaciones.
- MCP, cuando exista, DEBE ser un adaptador de entrada sobre los mismos casos de
  uso. NO PUEDE duplicar reglas ni obligar a modificar el dominio; si requiere una
  capacidad nueva, se añade un caso de uso.
- El dominio NO DEBE conocer la existencia de ningún adaptador.

**Razón**: es la decisión de ADR-003, enmendada por ADR-004 en el contrato de
interfaces (FastAPI y Typer desde H001) y completada por ADR-007 (persistencia
dual sin ORM) y ADR-008 (runtime en contenedores). Fijar la frontera permite
añadir MCP, PostgreSQL o contenedores sin reescribir reglas.

### IV. Puertos explícitos y composición única

`src/application/ports.py` DEBE declarar los puertos secundarios con
`typing.Protocol`, sin herencia obligatoria ni dependencias externas. En H003 el
puerto de persistencia es `IncidentRepositoryPort` y `ClockPort` ya cuenta con
`SystemClock`; `SlaPolicyPort` se incorporará cuando un caso de uso lo requiera,
con implementación y prueba reales.

`src/application/services.py` DEBE contener `IncidentService` y los casos de uso
vigentes en cada hito. En H003: triaje individual, resumen de activos, alta
persistente y auditoría de SLA. El triaje por lote queda en el ROADMAP y DEBE
añadirse como caso de uso cuando su hito lo requiera. El servicio SÓLO PUEDE
secuenciar, transaccionar y traducir entre puertos; NO DEBE contener reglas de
negocio, SQL ni detalles de transporte.

Los adaptadores de salida DEBEN ser intercambiables mediante `DATABASE_URL` sin
tocar dominio ni casos de uso. SQLite es el valor por defecto; PostgreSQL es un
motor aprobado por ADR-007 para H004. `src/adapters/outbound/factory.py` es el único
lugar que interpreta el DSN (`sqlite:///:memory:`, `sqlite:///ruta` o
`postgresql://`), instancia la clase concreta y la inyecta; ningún adaptador DEBE
autoconstruir sus dependencias de persistencia. Todo el SQL, DDL, siembra de
políticas y mapeo fila → entidad vive exclusivamente en
`src/adapters/outbound/`.

**Razón**: `typing.Protocol` mantiene el acoplamiento estructural y permite dobles
en memoria; una raíz de composición única hace que cambiar de motor sea un cambio
localizado y auditable.

### V. Stack gobernado y dependencias justificadas

- Python >= 3.10 gestionado con `uv`; `[tool.uv] package = false` e imports
  absolutos (`from src...`) resueltos desde la raíz del repositorio.
- REST: FastAPI + Pydantic v2. CLI: Typer. Servidor: Uvicorn.
- Persistencia: `sqlite3` de la biblioteca estándar como motor por defecto y
  `psycopg[binary]` para PostgreSQL, ambos sin ORM, conforme a ADR-001
  (parcialmente reemplazado por ADR-007). La selección se resuelve exclusivamente
  por `DATABASE_URL`; cualquier motor adicional DEBE tener un ADR aprobado antes
  de introducir su dependencia.
- Runtime: topología de referencia multi-contenedor con Docker Compose (`api` y
  `db: postgres:16-alpine`), conforme a ADR-008. La imagen de la API no contiene
  credenciales ni estado persistente; la base usa un volumen nombrado y un
  healthcheck real.
- La biblioteca estándar es la opción por defecto. Una dependencia nueva DEBE
  justificarse en el PR indicando qué problema resuelve y por qué no basta la
  estándar.
- Las versiones de Python y de las dependencias se fijan en `pyproject.toml` y
  `uv.lock`; no se instalan paquetes fuera de `uv`.

**Razón**: un stack pequeño y explícito mantiene el repositorio reproducible y
evita que el framework o el ORM se conviertan en el centro del sistema.

### VI. Fronteras verificadas estáticamente con Ruff

La verificación estática de fronteras es obligatoria y ejecutable:

```bash
uv run ruff check src/
```

El comando DEBE terminar sin errores antes de integrar. La configuración vive en
`pyproject.toml` (`[tool.ruff]` y `[tool.ruff.lint]`) y DEBE incluir reglas que
detecten, como mínimo:

1. Importaciones prohibidas en `src/domain/` (frameworks, persistencia, CLI,
   `pydantic`, `os.environ`).
2. Importaciones de `src.adapters` dentro de `src/application/`.
3. Importaciones de `src.adapters.outbound` o `src.adapters.inbound` concretos
   entre adaptadores cuando exista un puerto o caso de uso equivalente.

Desactivar una regla de frontera exige justificación en el PR y, si cambia la
topología, un ADR. La revisión manual sigue siendo obligatoria: Ruff complementa,
no sustituye, la regla de dependencia.

**Razón**: `typing.Protocol` no impone nada en tiempo de ejecución; sin una
verificación automática, la frontera hexagonal depende sólo de disciplina.

### VII. BDD obligatorio y pruebas ejecutables

Cada capacidad DEBE especificarse en español con escenarios `Given / When / Then`
y automatizarse con `pytest`. La verificación obligatoria es:

```bash
uv run pytest -v
```

Reglas:

- Las pruebas de aceptación atraviesan el adaptador de entrada o el caso de uso
  con dobles en memoria de los puertos.
- Las reglas de dominio tienen pruebas unitarias table-driven que cubren los
  límites exactos de las tablas de SLA y triaje.
- El tiempo es fijo e inyectado; NO se permite `sleep`, red, base de datos real ni
  `datetime.now()` en pruebas de dominio.
- Toda capacidad nueva o modificada DEBE traer sus escenarios; una capacidad sin
  pruebas ejecutadas y en verde NO se considera terminada.
- Los escenarios BDD son el contrato de aceptación: si el código y el escenario
  discrepan, se corrige el código o se enmienda el escenario con justificación,
  nunca se silencia la prueba.

**Razón**: el comportamiento operativo de IncidentOps (clasificación, SLA,
duplicados) es exactamente lo que se degrada en silencio; los escenarios
ejecutables son la única evidencia de que las interfaces comparten semántica.

## Restricciones Adicionales

### Invariantes de SLA

| Severidad | Minutos permitidos | Ventana | Escalamiento (75 %) |
|-----------|-------------------:|---------|--------------------:|
| P0        | 60                 | 24x7    | 45                  |
| P1        | 240                | 24x7    | 180                 |
| P2        | 480                | L-V 08:00-18:00 | 360        |
| P3        | 1440               | L-V 08:00-18:00 | 1080       |

- P2 y P3 SÓLO acumulan minutos dentro de la ventana hábil de lunes a viernes,
  08:00-18:00. Sábados, domingos y horas fuera de ventana no acumulan.
- Los días festivos no se contabilizan todavía: es deuda explícita (`TODO`) y
  exige un ADR y un puerto de calendario antes de implementarse.
- `elapsed_minutes` se trunca a minutos enteros.
- Incumplimiento estricto: `elapsed_minutes > allowed_minutes`; en el límite
  exacto no hay incumplimiento.
- Escalamiento: `status` activo, sin incumplimiento y
  `elapsed_minutes >= int(allowed_minutes * 0.75)`.
- `end_time = resolved_at or reference_time`. Si `reference_time < created_at`, es
  un error de dominio.
- Las fechas son naive consistentes; NO se mezclan `datetime` aware y naive.

### Estados del incidente

Estados canónicos: `OPEN`, `IN_PROGRESS`, `RESOLVED`, `CLOSED`.

- Activos: `OPEN`, `IN_PROGRESS`; son los únicos que aparecen en el resumen de
  activos.
- Terminales: `RESOLVED`, `CLOSED`; detienen el reloj de SLA y no escalan.
- `RESOLVED` y `CLOSED` exigen `resolved_at`.
- `INVESTIGATING` queda fuera del modelo; `IN_PROGRESS` es el único estado de
  trabajo en curso.

### Triaje, lote y duplicados

El triaje se basa en impacto real, nunca en palabras emocionales como "urgente" o
"hoy". La precedencia es P0 → P1 → P2 → P3; si ninguna regla aplica, el valor por
defecto es P2.

| Severidad | Criterio de impacto |
|-----------|---------------------|
| P0 | Indisponibilidad total/global/multi-tenant, pagos caídos, fuga de datos entre organizaciones |
| P1 | Saturación o timeouts de conexiones/pool, degradación severa del servicio |
| P2 | Lentitud medible, cuenta bloqueada, degradación acotada |
| P3 | Cosmética, staging, sin impacto operativo |

- El lote se procesa en orden ascendente de `created_at`; ante empate, por
  `incident_id` ascendente. El primero es el original.
- Duplicados: similitud `SequenceMatcher` sobre texto en minúsculas >= 0.75 dentro
  de la ventana de la severidad (P0 1 día, P1 2 días, P2 3 días, P3 4 días). Sólo
  cuentan candidatos con `0 <= created_at - prev_created_at <= ventana`.
- `duplicate_group_key` es el `incident_id` del original más antiguo, nunca el de
  otro duplicado; si el candidato ya es duplicado, se hereda su clave.
- La tabla exhaustiva de palabras y componentes es responsabilidad exclusiva de
  `src/domain/` y cambiarla exige pruebas de aceptación.

### Catálogo cerrado de equipos

| Componente | Equipo |
|------------|--------|
| `payments-gateway` | `Backend-Core` |
| `auth-identity` | `Security-IAM` |
| `database-cluster` | `Data-DBA` |
| `infra-certificates` | `Platform-SRE` |
| `security-audit` | `Security-IAM` |
| `reporting-api` | `otros` |

`otros` es el único valor de reserva; no es un equipo con guardia ni una vía para
evadir el catálogo. Añadir o retirar un equipo exige ADR y pruebas de aceptación.

### Contrato de persistencia entre motores

- Ambos motores DEBEN implementar el mismo `IncidentRepositoryPort` y compartir
  la semántica de errores y de escritura; ningún adaptador DEBE calcular SLA,
  similitud, claves de duplicado ni ordenar resultados.
- `created_at` y `resolved_at` se persisten como texto ISO 8601 naive normalizado
  a microsegundos (`YYYY-MM-DDTHH:MM:SS.ffffff`) en ambos motores. NO se usan
  `TIMESTAMP`, `TIMESTAMPTZ`, épocas numéricas ni zonas horarias del servidor.
- La ruta de alta usa `INSERT` estricto; `REPLACE`, `UPSERT` y
  `ON CONFLICT DO UPDATE` están prohibidos. La violación de unicidad se traduce al
  mismo error de aplicación en ambos motores.
- El DDL y los índices son idempotentes y equivalentes por motor; las consultas
  nuevas usan columnas explícitas y su plan se verifica con el motor real.
- El cerrojo por componente es de proceso. La topología de referencia mantiene una
  sola réplica de la API; escalar a varias réplicas exige un ADR de bloqueo
  distribuido.
- Un ORM o una herramienta de migración automática DEBE justificarse en un ADR.

### Deuda deliberada

- La deuda pedagógica de la Semana 1 (`SELECT *`, filtrado en Python y N+1 en
  `get_active_incidents_summary`) quedó retirada en H002. NO DEBE reintroducirse
  en los adaptadores ni replicarse en el dominio.
- `legacy/triage_rules.py` es una copia histórica congelada: NO DEBE importarse ni
  tratarse como fuente de verdad.
- `CONTEXT_LOG.md` es la bitácora calificada de ingeniería de prompts: NO DEBE
  reescribirse como relleno ni regenerarse de forma automática.

## Flujo de Desarrollo y Puertas de Calidad

Un PR NO se integra si incumple cualquiera de estas condiciones:

1. `uv run ruff check src/` termina sin errores y las reglas de frontera siguen
   activas.
2. `uv run pytest -v` pasa completo, incluidos los escenarios BDD de la capacidad
   tocada.
3. El dominio no importa frameworks, persistencia, CLI, `pydantic` ni relojes
   implícitos.
4. No hay tipos ni reglas de negocio duplicados fuera de `src/domain/`.
5. REST, CLI y el futuro MCP comparten el mismo caso de uso.
6. Toda decisión estructural tiene ADR en `docs/adr/` con diagrama Mermaid cuando
   aclare fronteras; si el ADR contradice esta Constitución, primero se enmienda
   la Constitución.
7. La documentación afectada (`AGENTS.md`, `README.md`, `ROADMAP.md`) se actualiza
   en el mismo PR.
8. Código, docstrings y documentación se mantienen en español.

Los cambios se desarrollan en la rama actual y se integran por PR
a `main`. No se dejan dos formas competidoras de invocar una capacidad: al migrar
un módulo legado se retira o reemplaza su punto de entrada en el mismo PR.

## Gobernanza

Esta Constitución prevalece sobre ADRs, código, `AGENTS.md`, `README.md`,
`ROADMAP.md` y `CONTEXT_LOG.md`. Si una práctica vigente la contradice, la
práctica se corrige; no se interpreta la Constitución para acomodarla.

**Procedimiento de enmienda**:

1. Abrir un PR con la propuesta y, si cambia una frontera o una decisión
   estructural, un ADR que la justifique.
2. Si un ADR en conflicto ya existe, enmendar primero la Constitución y luego
   ajustar el ADR.
3. Actualizar el bloque de versión y las fechas; generar el Sync Impact Report
   temporal y retirarlo antes de fusionar.
4. Revisión y aprobación por el mantenedor del repositorio. No hay enmiendas por
   commit directo a `main`.

**Política de versionado** (semántica `MAJOR.MINOR.PATCH`):

- **MAJOR**: eliminación o redefinición incompatible de un principio, sección o
  invariante de negocio.
- **MINOR**: principio o sección nueva, o ampliación material de una guía
  existente.
- **PATCH**: aclaraciones, correcciones de redacción o refinamientos que no
  cambian obligaciones.

**Revisión de cumplimiento**:

- Cada PR DEBE declarar cómo cumple las puertas de calidad y adjuntar la evidencia
  de los comandos ejecutados.
- La revisión verifica los ocho puntos de "Flujo de Desarrollo y Puertas de
  Calidad"; una violación bloquea la fusión, no se registra como deuda.
- Una capacidad nueva no se acepta sin escenarios BDD en verde y sin ADR cuando
  corresponda.
- La Constitución se revisa al cerrar cada reto del ROADMAP; si el reto cambió el
  stack, las fronteras o los invariantes, la revisión termina en enmienda.

**Guía operativa**: `AGENTS.md` describe comandos y convenciones de ejecución;
esta Constitución describe obligaciones. Ante conflicto, prevalece la
Constitución.

**Version**: 1.2.0 | **Ratified**: 2026-11-22 | **Last Amended**: 2026-11-23
