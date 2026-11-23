---
name: bdd-acceptance
description: Redacta escenarios BDD estilo Dan North (Dado / Cuando / Entonces) en la especificación con lenguaje ubicuo de negocio y los mapea uno a uno a pruebas test_bdd_* con TestClient y CliRunner sobre almacenamiento aislado. Úsala al escribir o revisar especificaciones de aceptación, al crear pruebas de aceptación para REST o CLI, o al depurar pruebas que comparten estado entre sí.
---

# Aceptación BDD en IncidentOps

## Cuándo usar esta skill

- Vas a escribir o revisar la sección de escenarios de una especificación
  (`specs/hNNN-*.md`; también llamada `spec.md` en los comandos de Spec Kit).
- Implementas o completas pruebas de aceptación para el adaptador REST (FastAPI) o el
  adaptador CLI (Typer).
- Detectas escenarios sin prueba, pruebas sin escenario o pruebas que comparten
  almacenamiento y dependen del orden de ejecución.
- Necesitas justificar ante el PR que cada escenario de la especificación está
  cubierto y es trazable.

La fuente de verdad es `docs/constitution.md` §3.2 (BDD y pruebas) y §3.3 (puertas de
calidad), más la especificación del hito. Esta skill es la guía operativa.

## 1. Principio: el escenario describe negocio, la prueba demuestra el borde

Un escenario responde **qué hace el sistema para quien lo usa**, no **cómo está
programado**. La prueba recorre el adaptador de entrada real y comprueba solo lo
observable por ese borde.

```text
especificación (lenguaje de negocio)
        │  1 escenario = 1 comportamiento = 1 función test_bdd_*
        ▼
prueba de aceptación (TestClient | CliRunner)
        │  entra por REST o por CLI, nunca por dentro
        ▼
caso de uso + dominio reales (con dobles solo en puertos de salida)
```

Reglas duras:

- Una prueba de aceptación no importa `src.domain`, `src.application` ni el
  repositorio concreto para invocarlos directamente. Entra por HTTP o por CLI.
- Los dobles se colocan en los **puertos de salida** (reloj, repositorio, política de
  SLA). Nunca se sustituye el caso de uso ni el dominio.
- Se permiten dobles de la raíz de composición en el borde
  (`src.composition.build_incident_service` o su equivalente en el factory) para
  inyectar almacenamiento aislado; es cableado, no regla de negocio.
- Nada de red real, base de datos compartida, `sleep` ni reloj del sistema. El tiempo
  entra fijo e inyectado.

## 2. Cómo redactar el escenario (estilo Dan North)

### 2.1 Forma

Un encabezado con identificador estable y un título en tercera persona que enuncie el
comportamiento; después un párrafo con las tres cláusulas en negrita y una sola frase
por cláusula.

```markdown
### E-05 — Un incidente registrado sigue visible para el equipo de guardia

**Dado** que el equipo de guardia registró el incidente `INC-2001` de la pasarela de
pagos con severidad `P0`,
**Cuando** consulta el resumen de incidentes activos de la pasarela de pagos,
**Entonces** el resumen incluye `INC-2001` con severidad `P0` y estado de SLA
`en plazo`.

**Prueba**: `tests/test_bdd_h002_resumen.py::test_bdd_e05_incidente_registrado_sigue_visible`
```

- **Identificador**: `E-NN` consecutivo dentro de la especificación. Nunca se reutiliza
  ni se renumera: es la clave de trazabilidad con la prueba.
- **Título**: declara el comportamiento, no la función que lo implementa. "Un
  incidente registrado sigue visible", no "`get_active_incidents_summary` devuelve la
  fila".
- **Dado**: estado previo concreto y verificable. Datos reales de ejemplo
  (`INC-2001`, `payments-gateway`, `P0`), no "un incidente cualquiera".
- **Cuando**: exactamente **una** acción del usuario o del sistema externo. Si
  aparecen dos acciones encadenadas, son dos escenarios.
- **Entonces**: resultados observables por el borde: severidad, componente, equipo,
  estado de SLA, código de error, código de salida. Nada de llamadas internas.
- **Y**: solo para añadir observaciones del mismo resultado, nunca para esconder un
  segundo comportamiento.
- **Prueba**: ruta y nombre exacto de la función que lo cubre. Sin esto el escenario
  está incompleto.

Longitud objetivo: entre 3 y 7 líneas de cuerpo. Si no cabe, el comportamiento es
demasiado grande: divídelo.

### 2.2 Lenguaje ubicuo, no vocabulario de implementación

El escenario usa el vocabulario del negocio y del contrato de interfaz. La
especificación mantiene un glosario breve con los términos admitidos (incidente,
reporte, severidad, componente, equipo de guardia, estado de SLA, resumen de activos).

**Sí se permite** (es vocabulario del negocio o del contrato público):

- Entidades y estados del negocio: incidente, reporte, severidad `P0`, estado de SLA.
- Campos del contrato publicado: `incident_id`, `raw_text`, `severity`,
  `recommended_team`, `duplicate_group_key`.
- Superficie de interfaz: `POST /api/v1/incidents/triage`, `triage --raw-text`,
  código de salida `2`, `application/problem+json`, código `TRIAGE_TEXTO_VACIO`.

**Nunca se permite** (filtra implementación):

- Clases, funciones, módulos o rutas de Python: `IncidentService`,
  `TriageResult`, `classify_impact`, `src.adapters.outbound.sqlite`,
  `build_incident_service`.
- Tablas, columnas, índices o SQL: `INSERT INTO incidents`, `status = 'OPEN'`,
  `SELECT *`, nombres de migraciones.
- Frameworks y librerías: Pydantic, Starlette, Typer, `httpx`, `sqlite3`.
- Nombres de fixtures, mocks o dobles: `cliente_http`, `monkeypatch`,
  `InMemoryIncidentRepository`.
- Detalles de configuración interna: variables de entorno, rutas de archivos de base
  de datos, puertos.

Contraejemplo que **no** se acepta:

```markdown
### E-05 — IncidentRepository.get_active_incidents_summary devuelve la fila

**Dado** un registro en la tabla `incidents` con `status = 'OPEN'`,
**Cuando** `IncidentService` ejecuta `SELECT * FROM incidents`,
**Entonces** el objeto `SLAEvaluation` tiene `breached = False`.
```

Reescritura aceptable:

```markdown
### E-05 — Un incidente activo aparece en el resumen del componente

**Dado** que el equipo de guardia registró un incidente activo de la pasarela de pagos
con severidad `P0` y SLA en plazo,
**Cuando** consulta el resumen de incidentes activos de la pasarela de pagos,
**Entonces** el resumen incluye ese incidente con severidad `P0` y SLA en plazo.
```

### 2.3 Una interfaz por escenario; la paridad es su propio escenario

Un escenario declara por dónde entra la acción (`Cuando` nombra el endpoint o el
subcomando). La equivalencia entre REST y CLI es un escenario aparte que compara las
dos salidas, como hace E-04 en H001.

No redactes "el sistema, por cualquier interfaz, clasifica…": la prueba no sabría qué
borde recorrer y acabaría duplicando aserciones dentro de una sola función.

### 2.4 Variantes de datos

Si el mismo comportamiento se repite con varios ejemplos, usa un esquema con tabla de
ejemplos dentro del mismo escenario, no un escenario por fila:

```markdown
### E-05 — Una entrada vacía se rechaza con un código estable

| Campo | Valor | Código esperado |
|-------|-------|-----------------|
| `raw_text` | `"   "` | `TRIAGE_TEXTO_VACIO` |
| `incident_id` | `""` | `TRIAGE_ID_VACIO` |
```

Sigue siendo **un** escenario y **una** función `test_bdd_*`, parametrizada con
`@pytest.mark.parametrize`. La tabla de ejemplos no rompe el 1:1.

### 2.5 Dónde vive el escenario

- Sección `## N. Escenarios BDD` de la especificación del hito
  (`specs/hNNN-*.md`).
- Cada escenario abre con `### E-NN — <título>`.
- Al cierre de la sección, una tabla de trazabilidad:

  | Escenario | Comportamiento | Prueba |
  |-----------|----------------|--------|
  | E-01 | Caída de pagos es P0 | `test_bdd_e01_...` |

- Los escenarios son la fuente de la verdad de la aceptación. Si el código y el
  escenario discrepan, se corrige el código o se enmienda la especificación con una
  nota de decisión; nunca se "arregla" la prueba para que pase.

## 3. Mapeo 1:1 a `test_bdd_*`

### 3.1 Convención de nombres

- Archivo: `tests/test_bdd_<hito>_<capacidad>.py`, por ejemplo
  `tests/test_bdd_h002_resumen.py`.
- Función: `test_bdd_e<NN>_<slug_en_snake_case>`; el identificador del escenario es
  obligatorio y va justo después del prefijo.
- `slug` en español, sin acentos ni eñes, en minúsculas.
- Docstring: el título del escenario, literal, precedido de `E-NN:`.
- Comentarios internos: `# Dado`, `# Cuando`, `# Entonces`, alineados con las
  cláusulas de la especificación.

```python
def test_bdd_e01_la_caida_de_pagos_es_p0(cliente_http: TestClient) -> None:
    """E-01: una caída de la pasarela de pagos se clasifica como P0 y va a Backend-Core."""
    # Dado un reporte de indisponibilidad total en la pasarela de pagos
    reporte = {"incident_id": "INC-1001", "raw_text": TEXTO_P0}

    # Cuando el reporte se envía al triaje por HTTP
    respuesta = cliente_http.post(RUTA, json=reporte)

    # Entonces la respuesta confirma P0, componente y equipo
    assert respuesta.status_code == 200, "E-01"
    resultado = respuesta.json()
    assert resultado["severity"] == "P0", "E-01"
    assert resultado["component"] == "payments-gateway", "E-01"
    assert resultado["recommended_team"] == "Backend-Core", "E-01"
```

Reglas del mapeo:

- **Un escenario, una función.** No agrupes E-01 y E-02 en la misma prueba ni partas
  E-03 en tres funciones por cada campo: usa `parametrize` dentro de la misma función.
- **Una función, un escenario.** Si una prueba no tiene `E-NN` en el nombre, es
  unitaria, de contrato o de paridad transversal; no la presentes como aceptación BDD.
- **Trazabilidad literal**: el número de la función coincide con el de la
  especificación y el docstring repite el título. Un revisor debe poder ir del
  escenario a la prueba con una búsqueda.
- **Aserciones con mensaje**: incluye el `E-NN` en el mensaje del `assert` para que un
  fallo en CI diga qué escenario se rompió.
- **Sin `skip`, `xfail` ni `assert True`.** Si algo no se puede probar todavía, no es
  un escenario de este hito: sácalo a la especificación futura.
- **Ejecución selectiva documentada**:
  `uv run pytest tests/test_bdd_h002_resumen.py -k test_bdd_e05`.

Estado actual del repositorio: `tests/test_spec_001_triage.py` ya cumple el 1:1 y la
trazabilidad, pero usa el prefijo `test_e01_…`. La convención `test_bdd_eNN_…` aplica a
todo escenario nuevo. Renombra la suite existente solo si el reto lo pide de forma
explícita, para no mezclar refactor cosmético con la capacidad en curso.

### 3.2 Plantilla de la función

```python
def test_bdd_eNN_<slug>(<pinza_de_interfaz>) -> None:
    """E-NN: <título literal del escenario>."""
    # Dado <estado inicial concreto>
    # Cuando <una acción por el borde>
    # Entonces <resultados observables>
```

Nada de lógica de negocio en la prueba: si necesitas calcular el valor esperado
(aplicar reglas de SLA, comparar textos por similitud), el escenario está mal
planteado o la expectativa debe venir escrita en la especificación como dato.

## 4. Pinzas de interfaz: TestClient y CliRunner

Se reutilizan las pinzas de `tests/conftest.py`. No instancies adaptadores dentro de la
prueba ni levantes `uvicorn`.

### 4.1 REST con `TestClient`

```python
from fastapi.testclient import TestClient

from src.adapters.inbound.api.app import create_app


def test_bdd_e01_...(cliente_http: TestClient) -> None:
    respuesta = cliente_http.post("/api/v1/incidents/triage", json=reporte)
```

- Usa siempre `create_app(service)` para poder inyectar el almacenamiento aislado; el
  `app` de módulo se construye al importar y no admite sustitución posterior.
- Afirma `status_code`, `content-type` cuando es contractual y los campos del
  documento. No compares el JSON completo salvo en la prueba de paridad.

### 4.2 CLI con `CliRunner`

```python
from typer.testing import CliRunner

from src.adapters.inbound.cli import app


def test_bdd_e04_...(runner_cli: CliRunner) -> None:
    salida = runner_cli.invoke(app, ["triage", "--incident-id", "INC-1001", "--raw-text", TEXTO_P0])
    assert salida.exit_code == 0
```

- Afirma `exit_code`, `stdout` (JSON parseado, nunca texto formateado a ojo) y
  `stderr` para los errores.
- Para `stdin`, usa `runner_cli.invoke(app, [...], input=texto)`; para archivos,
  `tmp_path`, nunca rutas de `data/`.
- El adaptador CLI construye el servicio por dentro. Para aislar el almacenamiento,
  parchea **el símbolo de cableado del módulo del borde**
  (`src.adapters.inbound.cli.build_incident_service`), no el caso de uso ni el
  repositorio.

### 4.3 Escenario de paridad

La paridad se prueba comparando salidas del mismo estado, no revisando el código:

```python
respuesta = cliente_http.post(RUTA, json=reporte)
salida = runner_cli.invoke(app, ["triage", "--incident-id", reporte["incident_id"],
                                 "--raw-text", reporte["raw_text"]])

assert salida.exit_code == 0
assert json.loads(salida.stdout) == respuesta.json()
```

Diferencias permitidas entre interfaces: código HTTP, cabeceras, formato de
`stdout`/`stderr`, flags y códigos de salida. Prohibidas: severidad, componente,
equipo, estado de SLA, `duplicate_group_key` y códigos de error.

## 5. Almacenamiento aislado

H001 es stateless y `tests/conftest.py` no necesita almacenamiento. Desde H002/H003,
toda prueba que registre o consulte estado debe recibir un almacén **nuevo por
prueba**, nunca compartido entre funciones, módulos o sesiones.

### 5.1 Regla general

1. **Ámbito `function`** para el almacén. Un almacén de ámbito `session` o `module`
   hace que el orden de ejecución altere el resultado.
2. **Una sola instancia por prueba**, compartida por HTTP y CLI cuando el escenario
   cruza interfaces; si cada borde recibe un almacén distinto, la paridad es falsa.
3. **Sembrar por operaciones de negocio o por fixture explícita**, no con SQL. Un
   `INSERT` en una prueba de aceptación acopla el escenario al esquema y filtra
   vocabulario prohibido.
4. **Nada de rutas fijas.** `data/sample_incidents.json` es entrada de solo lectura
   para clasificar, no almacenamiento. Prohibido escribir en `data/`, en la raíz del
   repo o en una base de datos "de desarrollo".
5. **Sin estado residual**: `tmp_path` se limpia solo; si usas un archivo propio,
   bórralo en el teardown. `monkeypatch` restaura variables de entorno al terminar.
6. **Sin dependencia de identificadores autogenerados**: afirma sobre identificadores
   de negocio (`INC-2001`), no sobre el `rowid`.
7. **Sin tiempo real**: inyecta el reloj por el puerto; el escenario declara la hora
   de referencia como dato.

### 5.2 Patrón preferido: doble en memoria inyectado en ambos bordes

```python
# tests/conftest.py (extensión prevista para H002/H003; ajusta a las firmas reales)
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import app as cli_app
from src.application.services import IncidentService
# from src.adapters.outbound.memory import InMemoryIncidentRepository


@pytest.fixture()
def servicio_aislado() -> IncidentService:
    """Almacén nuevo por prueba; ningún estado sobrevive al test."""
    return IncidentService(repository=InMemoryIncidentRepository())


@pytest.fixture()
def cliente_http(servicio_aislado: IncidentService) -> TestClient:
    return TestClient(create_app(servicio_aislado))


@pytest.fixture()
def runner_cli(servicio_aislado: IncidentService, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setattr(
        "src.adapters.inbound.cli.build_incident_service",
        lambda: servicio_aislado,
    )
    return CliRunner()
```

Con esto, un escenario que registra por HTTP y consulta por CLI ve exactamente el mismo
estado, y la siguiente prueba empieza vacía.

### 5.3 Variante con SQLite temporal por variable de entorno

Cuando el adaptador concreto se construye a partir de configuración:

```python
@pytest.fixture()
def almacen_sqlite(tmp_path, monkeypatch) -> Path:
    ruta = tmp_path / "incidentops-test.db"
    monkeypatch.setenv("INCIDENTOPS_DB_PATH", str(ruta))
    return ruta
```

- El nombre de la variable debe estar documentado en la especificación y usado por la
  raíz de composición/factory, no leído desde el dominio.
- `CliRunner.invoke(..., env={...})` también sirve, pero `monkeypatch` es preferible
  porque garantiza la restauración.
- El esquema se crea en el arranque del adaptador o por su API pública, nunca con DDL
  copiado en la prueba.

### 5.4 Anti-patrones de aislamiento

| Anti-patrón | Consecuencia |
|-------------|--------------|
| Compartir `cliente_http` de sesión con estado persistente | Una prueba ve datos de otra; fallos fantasma en CI |
| Escribir en `data/` o en `incidents.db` de la raíz | Estado sucio en el repo y pruebas no reproducibles |
| Sembrar con `INSERT INTO ...` en la prueba de aceptación | Acoplamiento al esquema y vocabulario de implementación |
| Inyectar almacenes distintos a HTTP y CLI en un escenario de paridad | La paridad compara estados diferentes y no prueba nada |
| `time.sleep` esperando un vencimiento de SLA | Prueba lenta y frágil; inyecta el reloj |
| Borrar tablas en `teardown` sobre una base compartida | Condición de carrera y orden implícito |

## 6. Flujo de trabajo

1. Lee la especificación del hito y localiza la sección de escenarios.
2. Verifica que cada escenario tenga `E-NN`, título de comportamiento y vocabulario de
   negocio. Reescribe los que filtren clases, SQL o frameworks.
3. Añade o corrige el enlace **Prueba** de cada escenario.
4. Implementa `test_bdd_eNN_*` en `tests/test_bdd_<hito>_<capacidad>.py` usando las
   pinzas de interfaz y el almacén aislado.
5. Ejecuta la prueba sola (`-k test_bdd_eNN`), luego el archivo, luego la suite:
   `uv run pytest`.
6. Comprueba que la suite pasa también al ejecutar las pruebas en orden inverso o una
   por una; si falla, hay estado compartido.
7. Actualiza la tabla de trazabilidad y, si cambió el contrato, `AGENTS.md` y el ADR
   correspondiente en el mismo PR.

## 7. Checklist antes de cerrar un cambio

- [ ] Cada escenario tiene identificador `E-NN`, título de comportamiento y una sola
      acción en el `Cuando`.
- [ ] El escenario usa vocabulario de negocio o de contrato; no menciona clases,
      funciones, módulos, tablas, columnas, SQL, frameworks ni fixtures.
- [ ] Cada escenario enlaza una función `test_bdd_eNN_*` y cada función cita su
      escenario en el nombre y en el docstring.
- [ ] La prueba entra por `TestClient` o `CliRunner`; no invoca dominio, aplicación ni
      repositorio concretos.
- [ ] El almacenamiento es nuevo por prueba y compartido entre bordes cuando el
      escenario cruza interfaces.
- [ ] No hay `sleep`, red real, rutas fijas, `INSERT` de siembra ni identificadores
      autogenerados en las aserciones.
- [ ] Los `assert` llevan el `E-NN` en el mensaje.
- [ ] La prueba pasa sola, en su archivo y en la suite completa: `uv run pytest`.
- [ ] La tabla de trazabilidad de la especificación está actualizada.
- [ ] Código, docstrings y documentación en español; `CONTEXT_LOG.md` no se reescribe.

## 8. Referencias del repositorio

- `docs/constitution.md` §3.2 y §3.3.
- `specs/h001-triaje-multi-interfaz.md` §8 (escenarios E-01 a E-08) y §9 (plan de
  pruebas).
- `tests/conftest.py` (pinzas `cliente_http`, `runner_cli`, `reportes_muestra`).
- `tests/test_spec_001_triage.py` (mapeo 1:1 y prueba de paridad HTTP/CLI).
- `.opencode/skills/hexagonalarchitecture/SKILL.md` §3 (paridad entre adaptadores).
