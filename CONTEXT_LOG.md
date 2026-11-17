# Bitácora de Ingeniería de Prompts y Contexto — Semana 1 (`CONTEXT_LOG.md`)

**Estudiante(s)**: `Diego Fernando Betancourt Cruz`  
**Fecha**: `2026-11-16`  
**Modelos / Asistentes Utilizados**: `Gemini Automático - Nivel de pensamiento: Medio`

---

## 1. De Prompts Pobres a Técnicas Clásicas de *Prompt Engineering* (Reto 1: `src/triage_rules.py`)

### 1.1 Diagnóstico de un Prompt Pobre y Ambiguo
Analiza el siguiente prompt deficiente para el Reto 1:
> *"El archivo `triage_rules.py` funciona mal con algunos tickets del JSON. Agrégale el equipo recomendado y una clave para duplicados, y no pongas P0 cuando no sea urgente."*

Documenta al menos **3 modos de fallo o ambigüedades** de este prompt (p. ej., ausencia de contexto de dominio, restricciones negativas difusas, falta de enumeración de equipos válidos o ausencia de ejemplos canónicos):
1. **Ausencia de contexto**: Falta agregar contexto para indicarle a la IA que funciona mal con el archivo y hace falta específicar el JSON de entrada.
2. **Uso de restricciones negativas difusas**: El texto "y no pongas P0 cuando no sea urgente." suena confuso, puede confundir a quien también lee la conversación con la IA, sugiero que se use "Pon P0 cuando sea urgente".
3. **Ambigüedad de valores**: Al indicarle a la IA que se agregue una clave para duplicados, no se es claro como debería ser la clave o que formato debe seguir, además no se sabe en donde pondrá la clave, en ambos incidentes o en el segundo. Sugiero ser expecífico como indicarle a la IA de si hay algún duplicado, debe poner la clave `is_duplicate=true` solo en los incidentes duplicados, se mantendrá como original el incidente más antiguo.

### 1.2 Uso de *Self-Consistency*, *Chain-of-Thought* y *Few-Shot Prompting*
- ¿Cómo utilizaste *Chain-of-Thought* (`<analysis>`) y *Self-Consistency* (múltiples consultas independientes) para definir las reglas de clasificación de los casos ambiguos (`INC-1002`, `INC-1007`, `INC-1009`) y la agrupación de duplicados (`INC-1001`/`INC-1006` e `INC-1003`/`INC-1008`)?
  - Al usar la etiqueta `<analysis>` el modelo razonó dando el siguiente paso a paso:
    1. Evaluación de alcance y criticidad
    2. Identificación de causas raíz y correlación
    3. Consolidación en grupos operativos
  Aunque esto variaba según el nivel de pensamiento utilizado.
  - Gracias a la múltiple ejecución de chats independendientes con la misma instrucción, para casos ambiguos se clasificará el riesgo de acuerdo al impacto, por ejemplo, si afecta a un usuario o si afecta a múltiples usuarios.
- Copia el prompt mejorado que empleaste aplicando las técnicas clásicas (`<role>`, `<domain_rules>` con justificación del *porqué*, `<examples>` *Few-Shot* y `<task>`):

```xml
<role>
Actúa como el encargado de gestionar los incidentes en la organización
</role>

<context>
<lsp_context symbol="classify_incident_report">
...
</lsp_context>
<lsp_context symbol="sla_calculator">
...
</lsp_context>
<lsp_context symbol="triage_rules">
...
</lsp_context>
</context>
<domain_rules>
Debemos clasificar reportes de incidentes en cuatro niveles de severidad:
- P0 (SLA 60 min, guardia 24/7): Indisponibilidad global de un servicio crítico (ej. pagos HTTP 502) o brecha activa de seguridad / fuga de datos entre organizaciones (multi-tenant).
- P1 (SLA 240 min, guardia 24/7): Degradación severa de infraestructura compartida con riesgo inminente de caída (ej. pool de conexiones de base de datos >90%).
- P2 (SLA 480 min, horario hábil L-V 08:00-18:00): Degradación moderada de rendimiento sin caída del servicio (ej. reportes lentos >3s) o bloqueo operativo que afecta únicamente a un usuario individual.
- P3 (SLA 1440 min, horario hábil): Solicitudes cosméticas de UI o tareas
preventivas de mantenimiento en entornos no productivos (staging). 

Importante (Por qué): La prioridad depende del impacto real sobre la
disponibilidad, la integridad de datos multi-tenant y el radio de afectación, nunca de palabras emocionales o de prisa subjetiva del usuario como "urgente" u "hoy".

Además, se debe asignar el incidente al equipo correspondiente, la clave se llama "recommended_team":
Backend-Core: Responsables de la lógica de negocio del sistema de pagos
Platform-SRE: Encargado de administrar la plataforma, arquitectura e integraciones necesarias para el funcionamiento del negocio
Data-DBA: Responsables de mantener la plataforma de datos.
Security-IAM: Gestionan los accesos de los diferentes usuarios y se encargan de la seguridad de la plataforma

Importante (Por qué): El equipo responsable asignado debe ser quien se encargue de solucionar el incidente, si el incidente no parece tener un responsable claro que no esté dentro de la lista asignada, por como equipo a "otros".

También detecta casos duplicados:
Si hay un 75% de similitud entre la descripción dos incidentes y debes marcar el incidente y los incidentes creados luego del original como duplicados con la clave "duplicate_group_key" y el valor que tomará es el "id" del incidente original.
También ten en cuenta la severidad y el tiempo de creación entre los posibles incidente duplicados para darlo como duplicado:
P0: Tiempo de creación menor a un día
P1: Tiempo de creación menor a dos días
P2: Tiempo de creación menor a tres días
P4: Tiempo de creación menor a 4 días

Importante (Por qué): Solo toma el incidente original (primer incidente creado) cómo válido a los demás, le pondrás la clave de duplicado
</domain_rules>

<examples>
<example>
<input>
id: INC-1001
Creación:  2026-11-05T08:15:00
Descripción: URGENTE: El gateway de pagos devuelve HTTP 502 Bad Gateway en todas las transacciones con tarjeta de crédito desde hace 12 minutos. Ningún comercio puede cobrar.

id: INC-1006
Creación: 2026-11-05T13:00:00
Descripción: Otra vez cayó la pasarela de cobros con tarjeta, a nuestros clientes les sale error 502 al intentar pagar el carrito de compras.
</input>
<analysis>
1. Radio de afectación: Pasarela de pagos sin funcionar
2. Radio de seguridad o caída: indispobilidad total
3. Duplicado: Ambos incidentes indican que no se pueden realizar pagos por lo cuál uno de los dos es duplicado
</analysis>
<output>
id: INC-1001 | severity: P0 | recommended_team: Platform-SRE 
id: INC-1006 | severity: P0 | recommended_team: Platform-SRE | duplicate_group_key: INC-1001
</output>
</example>
<example>
<input>
id: INC-1007
Creación: 2026-11-05T14:30:00
Descripción:Detectamos que al cambiar el parámetro company_id en la URL del reporte PDF se pueden visualizar facturas pertenecientes a otra organización.

</input>
<analysis>
1. Radio de afectación: Datos de los usuarios
2. Radio de seguridad o caída: exposición de los datos de los usuarios
3. Duplicado: No aplica
</analysis>
<output>
id: INC-1007 | severity: P0 | recommended_team: Security-IAM
</output>
</example>
</examples>

<task>
Refactoriza los archivos entregados de src/triage_rules.py y src/models.py para lograr el objetivo de asignar correctamente los valores de recommended_team, duplicate_group_key y severity.
</task>
```

---

## 2. Flujo Explorar $\rightarrow$ Destilar $\rightarrow$ Ejecutar en Contexto Limpio (Reto 2: Cálculo de SLA en Horario Hábil y ADR-002)

### 2.1 Exploración de Diseño (Sin Generar Código Aún) y Destilación
- **Objetivo explorado**: Diseño del algoritmo de cálculo de SLA en horario hábil (`P2`/`P3`, Lunes–Viernes 08:00–18:00) vs. 24/7 (`P0`/`P1`) y regla de escalamiento preventivo al 75%.
- **Síntesis de tu exploración de alternativas y resumen destilado (máx. 10 líneas)**:
  > Se le indicó al modelo posibles casos bordes de la deuda técnica, entre ellos, la creación de incidentes un día no laboral, creación del incidente fuera del horario laboral, la medida estándar sería de días, horas y minutos para dar legibilidad y que queda como deuda técnica incluir días festivos para el cálculo. Al momento de realizar el plan, la IA me sugirió el estándar de la zona horaria, a continuación el resumen destilado:
  
  ```
  Decisiones tomadas (Recomendación):
  Iteración por bloques de días: Calcular el SLA hábil (L–V, 08:00–18:00) mediante la intersección de la ventana laboral diaria, resolviendo limpiamente fines de semana, horas nocturnas y múltiples semanas.

  Deuda técnica controlada: Dejar los días festivos pendientes explícitamente con un # TODO para futura integración.

  Opciones descartadas:

  Iteración minuto a minuto: Descartada por su baja eficiencia en rendimiento ante incidentes abiertos por periodos prolongados.

  Cálculo matemático directo O(1): Descartada por su alta complejidad, propensión a errores en casos borde y baja legibilidad.
  ```

### 2.2 Ejecución con Contexto Curado en Nuevo Chat Limpio (*Context Engineering*)
Copia el prompt estructurado con etiquetas XML que utilizaste en un nuevo chat limpio para generar el **ADR (`docs/adr/002-calculo-sla-horario-habil.md`)** y la refactorización de `src/sla_calculator.py`:

```xml
<decision_summary>
Decisiones tomadas (Recomendación):
- Iteración por bloques de días: Calcular el SLA hábil (L–V, 08:00–18:00) mediante la intersección de la ventana laboral diaria, resolviendo limpiamente fines de semana, horas nocturnas y múltiples semanas.
- Deuda técnica controlada: Dejar los días festivos pendientes explícitamente con un # TODO para futura integración.
Opciones descartadas:
- Iteración minuto a minuto: Descartada por su baja eficiencia en rendimiento ante incidentes abiertos por periodos prolongados.
- Cálculo matemático directo O(1): Descartada por su alta complejidad, propensión a errores en casos borde y baja legibilidad.
</decision_summary>
<context>
<lsp_context symbol="evaluate_sla_status">
...
</lsp_context>
</context>
<constraints>
Incidentes creados fines de semana
Incidentes creados fuera del horario laboral
</constraints>
<task>
Redacta docs/adr/002-calculo-sla-horario-habil.md , incluyendo un diagrama Mermaid ( flowchart TD o stateDiagram-v2 ) que explique el cálculo y la transición a escalamiento siguiendo la plantilla adjunta
<task>
```

---

## 3. Tipos de Modelos y Matriz de Decisión Arquitectónica

### 3.1 Comparación de Tipos de Modelos
Compara el comportamiento que observaste al interactuar con:
1. **Modelo Rápido / Estándar (ej. Flash, Mini, Haiku o modo estándar)**:
2. **Modelo de Razonamiento Extendido (*Thinking Model*)**:
- ¿En cuál de las tareas de la semana fue indispensable el modelo de razonamiento y en cuál bastó el modelo rápido?

### 3.2 Matriz de Decisión Arquitectónica
Para la plataforma *IncidentOps* y su evolución futura, justifica qué paradigma es el adecuado en cada escenario:

| Escenario / Requerimiento | Paradigma Elegido (Código Determinista / ML Clásico / Asistente GenAI en Chat / LLM en Tiempo de Ejecución) | Justificación Técnica (Determinismo, Costo, Latencia, Riesgo de Alucinación) |
| :--- | :--- | :--- |
| 1. Contabilizar minutos hábiles transcurridos y verificar si un ticket superó el 75% de su SLA | | |
| 2. Explorar casos borde y redactar un ADR antes de modificar la arquitectura de consultas SQL | | |
| 3. Detectar anomalías numéricas en millones de métricas de CPU/RAM por minuto | | |
| 4. Clasificar reportes de incidentes redactados en lenguaje natural abierto cuando las reglas deterministas no cubren nuevos patrones | | |

---

## 4. Economía de Tokens y Curaduría de Contexto con `tiktoken` (LSP vs. `grep`/`read` vs. `glob`/`read`)

### 4.1 Medición Empírica en *IncidentOps*
Completa la tabla con los resultados obtenidos al auditar los símbolos con `uv run python -m src.context_audit --symbol evaluate_sla_status` (y `classify_incident_report`):

| Estrategia de Recolección de Contexto | Alcance (Archivos / Nodos) | Caracteres Totales | Tokens (`tiktoken o200k_base`) | % de Reducción vs. Fuerza Bruta |
| :--- | :--- | :---: | :---: | :---: |
| **1. Fuerza Bruta (`glob` + `read` todo)** | Todos los archivos del proyecto | | | 0% (Línea base) |
| **2. Búsqueda Textual (`grep` + `read` `.py`)** | Archivos `.py` donde aparece el símbolo | | | |
| **3. Semántica vía LSP (`definition` + `references` + `hover`)** | Solo definición, tipos asociados y líneas de invocación | | | |

### 4.2 Comparación de Formatos de Serialización (`--compare-formats`)
Registra los tokens medidos con `tiktoken` para los 10 incidentes en JSON indentado, JSON compacto, YAML y CSV, y explica qué formato elegirías al inyectar datos tabulares o logs largos en la ventana de contexto.
