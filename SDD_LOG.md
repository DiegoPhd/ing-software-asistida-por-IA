# Bitácora de Desarrollo Guiado por Especificaciones — Semana 2 (`SDD_LOG.md`)

**Estudiante(s)**: `Diego Fernando Betancourt Cruz`  
**Fecha**: `2026-11-22`  
**Modelos Utilizados en OpenCode (Plan/Razonamiento vs. Build/Implementación)**: `DeepSeek V4.1 Flash`

---

## 1. Elicitación con `/speckit.clarify` y Auditoría con `/speckit.analyze`

### 1.1 Feature `003-incident-lifecycle-sla`

- **Ambigüedades y casos borde detectados con `/speckit.clarify`**: `[3+ puntos concretos]`
    1. Cuando se consulta el SLA de un incidente ya resuelto con un instante de referencia anterior a su resolución, ¿qué valores debe devolver la consulta? (FR-020). Decide si la auditoría responde "cómo estaba el incidente en esa fecha" o "cuánto consumió al cerrarse"; cambia las pruebas de aceptación y, en una de las opciones, exige enmendar la Constitución antes de implementar.
    2. Si dos reportes equivalentes del mismo componente se registran casi al mismo tiempo, ¿qué garantía debe ofrecer el sistema? (FR-010) En una tormenta de alertas, dos peticiones simultáneas del mismo problema no deben producir dos incidentes sin aviso; define si la detección y el alta se serializan y qué debe demostrar la prueba de aceptación.
    3. Cuando un reporte recién registrado resulta ser más antiguo que incidentes activos equivalentes ya almacenados, ¿qué debe ocurrir con las claves de grupo de duplicados? (FR-014). Secide si el registro queda limitado a añadir el nuevo incidente o si puede reescribir registros previos para mantener un "original más antiguo" siempre vigente; cambia el alcance transaccional y las pruebas de grupos encadenados.
- **Hallazgos o validaciones de `/speckit.analyze` antes de implementar**: `[Resumen]`
    1. **C1, Critical**: Constitution (I / gate 4) - tasks.md:60 (T009); plan.md:132-133; data-model.md:12-14,21 - derivar_titulo(raw_text) — regla del campo persistido Incident.title (primera línea, máx. 200) — se implementa en src/adapters/inbound/lifecycle_contract.py. Data-model afirma que las reglas de la entidad viven en src/domain/models.py y que "ningún adaptador las redeclara"; Principio I y la puerta 4 exigen que toda regla de negocio esté en src/domain/.
    2. **C2, HIGH**: Constitution (II/IV) - tasks.md:57 (T006); plan.md:176, 81; constitution.md:43-44,83-86 - El instante inyectable se modela como now: Optional[Callable[[], datetime]] dentro de IncidentService, sin ClockPort. El Principio II admite "argumento explícito", pero el Principio IV dice que ClockPort "se incorporará cuando un caso de uso lo requiera", y H003 es exactamente ese hito. Ni plan ni ADR-006 justifican la desviación.
    3. **I1, HIGH**: Inconsistency (campo) - 	tasks.md:87 (T014) vs data-model.md:27,61 y spec.md:131 (FR-006) - T014 ordena "validar y recortar identificador y texto"; el modelo declara Incident.raw_text como "texto original sin normalizar" y FR-006 prohíbe normalizarlo. contracts/create-api.md aclara que el recorte es sólo para validar. Si se recorta el texto persistido se altera la base de la comparación de duplicados y la auditoría.

### 1.2 Feature `004-postgres-container-runtime`

- **Ambigüedades y RNF aclarados antes de diseñar PostgreSQL/Compose**: `[3+ puntos concretos]`

---

## 2. Comparación Crítica: SDD Manual (Iteración 1) vs. GitHub Spec Kit (Iteración 2 y Retos)

| Dimensión Comparada | SDD Manual (Iteración 1: `001`) | GitHub Spec Kit (Iteración 2 y Retos: `002`–`004`) |
| :--- | :--- | :--- |
| **Separación *QUÉ* vs. *CÓMO* vs. *TAREAS*** | Es complejo debido a que como usuario se le ingresa el prompt y pueden mezclarse capas, como lo son el problema y la solución técnica. | Funciona como un estándar entonces, mediante las plantillas y comando se tienen las capas bien definidas y limitadas en las diferentes fases. |
| **Gestión de ambigüedades (`/speckit.clarify`)** | En este caso las ambigüedades suelen detectarse en etapa de desarrollo, si bien, se intenta eliminarlas, no es lo suficientemente eficiente. | Mediante el comando y las instrucciones propias, se puede saber rápidamente que ambigüedades pude haber antes de planificar. |
| **Consistencia contra la Constitución (`/speckit.analyze`)** | Las guías o las convensiones no son claras siempre y pueden no estár alineadas con otros integrantes del equipo, se requiere hacer auditoria exhaustiva y manual | Se valida muy bien los diferentes manifiestos de la especificación, plan y tareas para encontrar convergencias o contradicciones, además, da la criticidad para solucionar estos problemas |
| **Riesgo de verbosidad / exceso de Markdown** | Esta considero que es una potencial ventaja del SDD manual, ya que los manifiestos son más cortos y consisos, sin embargo, puede dar lugar a ambigüesdades por la falta de detalle. | Los archivos son demasiado extensos como para hacer una validación humana, sin embargo, son muy específicos y claros.  |

- **Análisis basado en MartinFowler.com (Birgitta Böckeler)**:

1. De los tres niveles descritos por Böckeler (**Spec-first**, **Spec-anchored**, **Spec-as-source**), ¿en cuál ubicas este proyecto de *IncidentOps* y por qué?
    - **Spec-as-source** porque no se interviene en el código, si bien, se revisa, para hacer modificaciones al código, lo que se hace es revisar muy bien el paso a paso de las especificaciones, objetivos y/o criterios de aceptación. Hacer un cambio manual en el código, puede producir que no se estén respetando los manifiestos. 
2. Böckeler advierte que los *toolkits* SDD pueden generar "montañas de Markdown" difíciles de revisar para un humano. ¿Qué técnicas aplicaste (concisión en `docs/ROADMAP.md`, curaduría en `clarify`/`plan`/`tasks` y pruebas deterministas en `pytest`) para evitar aprobar especificaciones verbosas a ciegas?
    - Primeramente ejecuté clarify para cerrar varias brechas y ambigüedades, en algunas ocasiones fue necesario ejecutar el comando dos veces para hacer una revisión más exhaustiva, luego apliqué BDD para la generación de casos de prueba y realizar pruebas sobre esto con pytest permitió validar las implementaciones realizadas, considero que es una gran herramienta de validación para el Markdown

---

## 3. *Commands* vs. *Agent Skills*, Arquitectura Hexagonal, ADRs y Uso de *Reasoning*

- **Diferencia entre *Commands* (`/speckit.*`) y *Agent Skills* (`hexagonal-architecture`, `bdd-acceptance`, `adr-writer`)**: Explica cómo OpenCode carga las *skills* bajo demanda y por qué fue necesario seguir el orden causal ADR $\rightarrow$ Constitución $\rightarrow$ Hito tanto en clase (`ADR-003` antes de `docs/constitution.md`) como en el Reto 2 (`ADR-004` y actualización de `.specify/memory/constitution.md` antes de especificar e implementar el Hito `004`).
- **Valor de la Arquitectura Hexagonal**: Explica cómo compartir `IncidentService` e `IncidentRepositoryPort` facilitó exponer FastAPI, Typer y el adaptador PostgreSQL sin tocar el dominio (y cómo prepara la incorporación de futuros adaptadores).
- **Uso intencional de *Reasoning / Extended Thinking* en OpenCode**: ¿En qué comandos (`/speckit.clarify`, `/speckit.plan`, `/speckit.analyze`) aportó mayor valor el razonamiento extendido y en cuáles (`/speckit.implement`) resultó más eficiente un modelo rápido?
    - En este caso no aplica, dado que siempre utilicé el mismo modelo con el mismo esfuerzo el cual fue DeepSeek V4.1 Flash con esfuerzo en High
---

## 4. Evidencia de Verificación Determinista

- **Análisis estático de fronteras hexagonales (`uv run ruff check src/`)**:

```text
[Pega aquí la salida de uv run ruff check src/ mostrando All checks passed!]
```

- **Salida completa de `uv run pytest -v`**:

```text
[Pega aquí la salida completa de uv run pytest -v con el 100% de las pruebas en PASSED]
```

- **Evidencia de CLI Typer y containerización (`docker compose config` / `docker compose up --build`)**:

```text
[Pega aquí la salida de al menos dos subcomandos CLI y de docker compose]
```
