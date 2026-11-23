# Especificación de Funcionalidad: Ciclo de vida, duplicados y SLA

**Rama de la funcionalidad**: `diego.betancourt/reto-3` (pendiente de creación)

**Creado**: 2026-11-22

**Estado**: Borrador

**Entrada**: Descripción del usuario: "H003 — Ciclo de vida, duplicados y SLA. Necesitamos registrar los incidentes entrantes de forma persistente, avisar en la propia respuesta cuando ya existe otro incidente equivalente abierto (misma regla de duplicados de la Constitución §1.4), y consultar el estado de SLA de un incidente concreto en cualquier instante de referencia, tanto por API HTTP como por la herramienta CLI, con paridad de semántica y de valores entre ambos canales."

## Clarifications

### Session 2026-11-22

- Q: ¿Quién debe fijar el instante de creación del incidente que se registra? → A: El cliente lo indica; si lo omite, se usa el instante de la solicitud.
- Q: Si un nuevo reporte es más antiguo que incidentes equivalentes ya almacenados, ¿qué debe ocurrir con las claves de grupo existentes? → A: Dejar los registros previos intactos; el nuevo incidente actúa como original y no recibe clave.
- Q: Si un incidente ya está resuelto y se consulta su SLA en un instante anterior a su resolución, ¿qué debe devolver la consulta? → A: Los valores congelados en el instante de resolución; el instante de referencia sólo debe ser posterior o igual a la creación.
- Q: Si dos reportes equivalentes del mismo componente se registran casi al mismo tiempo, ¿qué garantía debe ofrecer el sistema? → A: Serializar por componente la detección y el alta, de modo que el segundo registro siempre informe al primero y ambos se persistan.

## Escenarios de Usuario y Pruebas *(obligatorio)*

### Historia de Usuario 1 - Registrar un incidente entrante de forma persistente (Prioridad: P1)

Como persona de guardia o integrador de monitoreo, necesito registrar el reporte de un incidente entrante de modo que quede almacenado, clasificado y disponible para consultas posteriores, para no perder la trazabilidad operativa entre una petición y otra.

**Por qué esta prioridad**: es la base de la capacidad; sin un registro duradero no existen duplicados que avisar ni SLA que auditar.

**Prueba independiente**: registrando un reporte válido por cualquiera de los dos canales y consultándolo después —incluido un reinicio del proceso sobre el mismo almacenamiento— el incidente se recupera con el mismo identificador, título, componente, severidad, estado y texto original.

**Escenarios de aceptación**:

1. **Dado** un reporte nuevo con identificador libre y sin incidentes equivalentes abiertos, **cuando** se registra por HTTP o por consola, **entonces** el alta responde 201 en HTTP, queda almacenado con la severidad, el componente y el equipo derivados de la clasificación por impacto vigente, en estado inicial `OPEN`, con el instante de creación indicado o el de la solicitud, e informa `is_duplicate=false` y `duplicate_of=[]` en ambos canales.
2. **Dado** un incidente registrado, **cuando** el servicio se detiene y vuelve a arrancar sobre el mismo almacenamiento, **entonces** el incidente sigue disponible con los mismos valores.
3. **Dado** un incidente registrado, **cuando** se consulta el resumen de incidentes activos, **entonces** aparece con los mismos datos con los que fue registrado, sin duplicarse ni alterarse.
4. **Dado** un identificador que ya corresponde a un incidente almacenado, **cuando** se intenta registrar un reporte con ese identificador, **entonces** el alta responde 409 y la consola termina con código de salida 1, el incidente previo queda intacto y no se modifica ningún otro dato.
5. **Dado** un reporte con identificador o texto vacío, compuesto sólo por espacios, o que excede las longitudes admitidas, **cuando** se intenta registrar, **entonces** responde 422 y la consola termina con código de salida 2, con un mensaje comprensible y sin persistir nada.

---

### Historia de Usuario 2 - Avisar de incidentes equivalentes abiertos en la misma respuesta (Prioridad: P1)

Como persona de guardia, necesito que la respuesta del registro me diga de inmediato si ya hay otro incidente abierto equivalente, para atender el original en lugar de duplicar el trabajo.

**Por qué esta prioridad**: evita el trabajo duplicado, que es el valor central del hito; el aviso debe llegar sin una consulta adicional.

**Prueba independiente**: con un incidente activo almacenado, se registra un reporte equivalente y la propia respuesta del registro indica que existe un equivalente abierto e identifica al original; con un reporte que difiere en texto, componente o ventana temporal, la respuesta no avisa.

**Escenarios de aceptación**:

1. **Dado** un incidente activo del componente `payments-gateway` cuyo texto es similar al nuevo reporte, **cuando** se registra el nuevo reporte con el mismo componente y dentro de la ventana de la severidad, **entonces** el alta responde 201 con `is_duplicate=true` y el identificador del incidente previo aparece en `duplicate_of`.
2. **Dado** un reporte equivalente cuyo incidente candidato está en estado terminal, **cuando** se registra, **entonces** el incidente terminal —incluido `RESOLVED`— se ignora y la respuesta informa `is_duplicate=false` y `duplicate_of=[]`.
3. **Dado** un reporte equivalente a un incidente activo de otro componente, **cuando** se registra, **entonces** la respuesta no lo informa como equivalente.
4. **Dado** un incidente activo cuyo texto difiere del nuevo reporte por debajo del umbral de similitud vigente, **cuando** se registra el nuevo, **entonces** no se informa como equivalente.
5. **Dado** un incidente activo equivalente pero cuya diferencia de instantes de creación excede la ventana de su severidad, **cuando** se registra el nuevo, **entonces** no se informa como equivalente.
6. **Dado** un incidente equivalente que ya pertenece a un grupo de duplicados, **cuando** se registra el nuevo, **entonces** el nuevo hereda la clave del grupo original y nunca la clave de otro duplicado.
7. **Dado** varios incidentes equivalentes abiertos, **cuando** se registra el nuevo, **entonces** `duplicate_of` los enumera ordenados de más antiguo a más reciente, con desempate por identificador ascendente, y el grupo de duplicados corresponde al original más antiguo.
8. **Dado** un registro que produce aviso de duplicados, **cuando** la operación termina, **entonces** el nuevo incidente igualmente queda registrado, no se fusiona ni se modifica ningún incidente existente y el aviso es informativo.
9. **Dado** dos reportes equivalentes que se registran de forma simultánea, **cuando** ambas operaciones terminan, **entonces** ambos quedan registrados y el segundo en confirmarse informa al primero con `is_duplicate=true` y su identificador en `duplicate_of`.

---

### Historia de Usuario 3 - Consultar el estado de SLA de un incidente concreto (Prioridad: P1)

Como responsable de operaciones o auditor, necesito conocer en cualquier instante de referencia cuánto SLA ha consumido o consumió un incidente concreto, si lo incumplió y si requiere escalamiento, para auditar decisiones pasadas o evaluar el estado presente.

**Por qué esta prioridad**: es la segunda mitad del objetivo del hito y la razón por la que un incidente registrado sirve más allá del momento de su creación.

**Prueba independiente**: sobre un incidente almacenado, una consulta con un instante de referencia explícito devuelve los minutos consumidos, el máximo permitido, los minutos restantes, el incumplimiento y el escalamiento, coherentes con la política vigente; en un incidente activo, repetir la consulta con otro instante produce el resultado correspondiente a ese instante.

**Escenarios de aceptación**:

1. **Dado** un incidente activo, **cuando** se consulta su SLA con un instante de referencia posterior a su creación, **entonces** la respuesta informa minutos consumidos, máximo permitido, minutos restantes, si hay incumplimiento y si requiere escalamiento, junto con el identificador, la severidad, el estado y el instante de referencia aplicado.
2. **Dado** un incidente activo P0, **cuando** se consulta su SLA con una diferencia de 60 minutos exactos desde su creación, **entonces** no aparece como incumplido y sus minutos restantes son cero.
3. **Dado** un incidente activo P0, **cuando** se consulta su SLA con 61 minutos, **entonces** aparece como incumplido y no como escalamiento pendiente.
4. **Dado** un incidente activo P1 con 180 minutos consumidos, **cuando** se consulta su SLA, **entonces** requiere escalamiento.
5. **Dado** un incidente activo P2 creado el viernes `2026-11-06T17:00:00`, **cuando** se consulta su SLA el lunes `2026-11-09T09:00:00`, **entonces** la respuesta informa `elapsed_minutes=120`, `allowed_minutes=480`, `remaining_minutes=360`, `is_breached=false` y `requires_escalation=false`, excluyendo noches y fin de semana.
6. **Dado** un incidente en estado terminal con instante de resolución registrado, **cuando** se consulta su SLA con cualquier instante de referencia posterior a su creación, **entonces** el cómputo se detiene en el instante de resolución y no crece con el instante de referencia.
7. **Dado** un instante de referencia anterior a la creación del incidente, **cuando** se consulta su SLA, **entonces** la consulta responde 422 y la consola termina con código de salida 1, sin entregar valores parciales ni negativos.
8. **Dado** un identificador que no corresponde a ningún incidente almacenado, **cuando** se consulta su SLA, **entonces** la consulta responde 404 y la consola termina con código de salida 1, informando el problema y sin entregar un documento parcial.
9. **Dado** un instante de referencia omitido, **cuando** se consulta el SLA, **entonces** se aplica el instante actual y la respuesta lo informa.

---

### Historia de Usuario 4 - Operar las tres capacidades desde la consola con paridad (Prioridad: P2)

Como ingeniero de guardia que trabaja por terminal o que automatiza diagnósticos, necesito registrar incidentes y consultar su SLA desde la consola con los mismos campos, la misma semántica y los mismos valores que por HTTP, para no cambiar de herramienta ni reinterpretar resultados.

**Por qué esta prioridad**: ambos canales son parte del contrato del hito, pero el valor operativo principal ya se entrega con las historias anteriores; esta historia garantiza que la consola no se convierta en una segunda verdad.

**Prueba independiente**: para los mismos datos y las mismas entradas, las respuestas exitosas de la consola y de HTTP coinciden campo por campo, y los fallos equivalentes producen el mismo código estable y la misma clase de error, sin resultados parciales.

**Escenarios de aceptación**:

1. **Dado** el mismo reporte entrante y el mismo instante de creación, **cuando** se registra por consola y por HTTP, **entonces** ambos canales devuelven el mismo `is_duplicate`, el mismo `duplicate_of` y la misma `duplicate_group_key`.
2. **Dado** el mismo incidente y el mismo instante de referencia, **cuando** se consulta el SLA por consola y por HTTP, **entonces** todos los campos y valores coinciden.
3. **Dado** un fallo de entrada, **cuando** el comando de consola termina, **entonces** informa el problema con el mismo código estable que el canal HTTP, un código de salida distinto de cero y sin imprimir un documento parcial.
4. **Dado** que la consola se ejecuta con éxito, **cuando** el resultado se entrega en la terminal, **entonces** la salida es un documento JSON legible por personas y consumible por scripts, con los mismos campos que el canal HTTP.
5. **Dado** un reporte nuevo y un incidente almacenado, **cuando** se ejecuta el comando de consola `create` para el alta y el comando `sla` para consultar su SLA, **entonces** ambos comandos producen los mismos documentos y valores que sus operaciones equivalentes por HTTP.

---

### Casos Límite

- **Frontera exacta de similitud**: dos textos con similitud exactamente igual al umbral vigente son equivalentes; un valor inmediatamente inferior no lo es, y ambos canales deben coincidir en esa decisión.
- **Frontera exacta de la ventana**: dos incidentes separados exactamente por la ventana de su severidad son candidatos; un segundo más de diferencia los excluye. Un candidato posterior al nuevo puede ser equivalente en texto y ventana, pero no se incluye en `duplicate_of` porque el aviso describe duplicados previos.
- **Ventana según la severidad**: la ventana aplicable es la de la severidad del incidente más antiguo del par, que es el que puede actuar como original.
- **Candidato sin texto original**: un incidente activo del mismo componente que no conserva el texto original no puede compararse y nunca produce aviso de duplicado.
- **Registro del original más antiguo**: si el nuevo registro precede a todos los equivalentes abiertos, actúa como original, no recibe clave, `is_duplicate=false` y `duplicate_of=[]`; los incidentes equivalentes posteriores no se reescriben.
- **Equivalente posterior**: un incidente equivalente creado después del nuevo no se incluye en `duplicate_of`, porque el aviso describe duplicados previos; el alta no lo marca como duplicado por ese incidente.
- **Aviso sin fusión**: un aviso de duplicado nunca modifica, elimina, fusiona ni reasigna el incidente original ni el nuevo.
- **Registro repetido del mismo identificador**: se rechaza como conflicto sin sobrescribir el incidente existente y sin alterar su texto, estado ni clave de grupo.
- **Registros simultáneos equivalentes**: dos altas concurrentes del mismo componente se serializan, de modo que la segunda ve a la primera y la informa; ninguna de las dos se rechaza por duplicidad.
- **Instante de creación futuro**: un incidente registrado con instante de creación posterior al instante actual no se rechaza por ese motivo; la coherencia temporal se evalúa al consultar su SLA.
- **Instante de referencia igual a la creación**: los minutos consumidos son cero, no hay incumplimiento y no hay escalamiento.
- **Instante de resolución incoherente**: un incidente terminal cuyo instante de resolución precede a su creación es un dato incoherente y la consulta de SLA se rechaza por completo.
- **Incidente terminal consultado en un instante anterior a su resolución**: el resultado sigue detenido en el instante de resolución, porque el reloj de SLA no retrocede; el instante de referencia sólo debe ser coherente con la creación.
- **Severidad o estado desconocidos en el almacenamiento**: la consulta de SLA se rechaza como incoherencia de datos, sin inventar valores por defecto.
- **Fechas con zona horaria**: tanto el instante de creación como el de referencia se rechazan si incluyen zona horaria, porque el sistema sólo admite instantes locales coherentes.
- **Filtros o campos no previstos**: un campo, parámetro u opción fuera del contrato se rechaza como entrada inválida, sin ignorarse en silencio.
- **Volumen alto**: con al menos 10.000 incidentes activos almacenados, el registro con su veredicto de duplicados y la consulta de SLA deben responder dentro del objetivo sin degradar la exactitud.

## Requisitos *(obligatorio)*

### Requisitos Funcionales

- **FR-001**: El sistema DEBE ofrecer el registro de incidentes entrantes por HTTP (`POST /api/v1/incidents`) y por consola (`create`) con la misma semántica, los mismos campos y los mismos valores; la igualdad verificable entre canales se fija en FR-021.
- **FR-002**: El sistema DEBE ofrecer la consulta del estado de SLA de un incidente concreto por HTTP (`GET /api/v1/incidents/{incident_id}/sla`) y por consola (`sla`) con la misma semántica, los mismos campos y los mismos valores.
- **FR-003**: Un registro válido DEBE persistirse de forma duradera: el incidente debe sobrevivir al reinicio del proceso y quedar visible para cualquier consulta posterior sobre el mismo almacenamiento.
- **FR-004**: El registro DEBE clasificar el reporte con la regla de triaje por impacto vigente, derivando severidad, componente y equipo responsable del texto original; el cliente no impone severidad, componente ni equipo.
- **FR-005**: El incidente registrado DEBE iniciar en estado `OPEN`. El instante de creación DEBE ser un campo opcional e idéntico en ambos canales, con el formato temporal estricto de FR-024; si se omite, se resuelve una sola vez el instante de la solicitud y se informa en la respuesta.
- **FR-006**: El registro DEBE conservar el texto original sin normalizar, porque es la base de comparaciones futuras y de la auditoría.
- **FR-007**: El título es opcional en la entrada; cuando se omite, se deriva del texto original de forma determinista y estable.
- **FR-008**: El identificador del incidente es obligatorio y único; un registro con un identificador ya existente DEBE rechazarse como conflicto (409 en HTTP, código de salida 1 en la consola) sin sobrescribir, fusionar ni alterar el incidente previo.
- **FR-009**: El registro DEBE rechazar identificadores o textos vacíos, compuestos sólo por espacios, o que excedan las longitudes admitidas, con 422 en HTTP y código de salida 2 en la consola, sin persistir nada.
- **FR-010**: El registro DEBE detectar incidentes equivalentes abiertos comparando sólo contra incidentes en estado `OPEN` o `IN_PROGRESS`, del mismo componente y distintos del propio incidente; los estados terminales `RESOLVED` y `CLOSED` quedan excluidos de la comparación.
- **FR-011**: Dos incidentes DEBEN considerarse equivalentes cuando la similitud de sus textos originales en minúsculas alcanza el umbral vigente de la Constitución y la diferencia entre sus instantes de creación, medida del más antiguo al más reciente, es cero o está dentro de la ventana de la severidad del más antiguo.
- **FR-012**: La respuesta del alta DEBE devolver los datos del incidente registrado (identificador, título, componente, severidad, equipo responsable, estado e instante de creación) junto con `duplicate_group_key`, `is_duplicate` y `duplicate_of`, y DEBE responder 201 aunque existan duplicados.
- **FR-013**: `duplicate_of` DEBE contener los identificadores de los incidentes equivalentes abiertos que preceden al nuevo en el orden canónico de creación (instante de creación ascendente y, en empate, identificador ascendente), ordenados de más antiguo a más reciente; los equivalentes posteriores no se incluyen y `is_duplicate` es verdadero si y sólo si `duplicate_of` no está vacío.
- **FR-014**: `duplicate_group_key` DEBE ser nula si `duplicate_of` está vacío; en caso contrario, el identificador del original más antiguo entre los incidentes precedentes o, si ese original ya es duplicado, la clave heredada de su grupo.
- **FR-015**: El registro NUNCA DEBE rechazarse por la existencia de duplicados, ni fusionar, modificar, reasignar o eliminar incidentes existentes; el aviso es informativo.
- **FR-016**: El registro DEBE ser atómico: o persiste el incidente completo con su clasificación y su clave de grupo, o no persiste nada y no informa un aviso parcial.
- **FR-017**: La consulta de SLA DEBE aceptar un identificador y un instante de referencia opcional en ISO 8601 local; si se omite, se resuelve el instante actual una sola vez y se informa en la respuesta.
- **FR-018**: La consulta de SLA DEBE devolver, como mínimo: `incident_id`, `severity`, `status`, `created_at`, `resolved_at` cuando exista, `reference_time`, `elapsed_minutes`, `allowed_minutes`, `remaining_minutes`, `is_breached`, `requires_escalation` y la ventana de cómputo aplicada.
- **FR-019**: Los valores de SLA DEBEN ser exactamente los de la política vigente: `P0` con 60 minutos y `P1` con 240 minutos en cómputo 24x7; `P2` con 480 minutos y `P3` con 1440 minutos en cómputo de lunes a viernes dentro de la ventana hábil; minutos enteros truncados.
- **FR-020**: El incumplimiento DEBE ser estrictamente mayor que el máximo permitido, el escalamiento DEBE exigir estado activo, ausencia de incumplimiento y al menos el 75 % del máximo permitido redondeado hacia abajo, y el fin del cómputo DEBE ser el instante de resolución si existe o el instante de referencia en caso contrario.
- **FR-021**: Para los mismos datos y las mismas entradas, los canales HTTP y consola DEBEN devolver campos, valores y veredictos idénticos; los fallos equivalentes DEBEN compartir código estable, clase de error y mapeo de estado HTTP a código de salida.
- **FR-022**: Una consulta de SLA con un instante de referencia anterior al instante de creación del incidente DEBE rechazarse por completo con 422 en HTTP y código de salida 1 en la consola, sin minutos negativos ni valores parciales.
- **FR-023**: Una consulta de SLA sobre un identificador inexistente DEBE rechazarse con 404 en HTTP y código de salida 1 en la consola, con un error de "no encontrado" claramente distinguible de una respuesta válida.
- **FR-024**: El instante de referencia y el instante de creación DEBEN expresarse como fecha y hora locales sin zona horaria, en ISO 8601 con separador `T`; un valor con zona horaria, formato distinto o tipo incorrecto DEBE rechazarse con 422 en HTTP y código de salida 2 en la consola.
- **FR-025**: La consulta de SLA DEBE ser una operación de sólo lectura: no modifica el incidente, su estado, su clave de grupo ni ningún otro dato.
- **FR-026**: Los estados terminales `RESOLVED` y `CLOSED` NO DEBEN escalar nunca y su cómputo de SLA DEBE detenerse en el instante de resolución, con independencia de que el instante de referencia sea anterior o posterior a esa resolución.
- **FR-027**: El registro y la consulta DEBEN usar las reglas canónicas de triaje, duplicados y SLA del núcleo, sin introducir umbrales, ventanas ni políticas paralelas.
- **FR-028**: Los errores DEBEN informar qué campo o parámetro falló y un mensaje comprensible, sin exponer detalles internos ni entregar documentos parciales.
- **FR-029**: Los canales DEBEN rechazar campos, parámetros u opciones que no formen parte de su contrato, en lugar de ignorarlos en silencio.
- **FR-030**: El registro DEBE serializar por componente la comprobación de equivalencias y la escritura del nuevo incidente, de modo que, si dos reportes equivalentes concurren, el que se confirma en segundo lugar informe al primero y ambos queden persistidos.

### Interfaces de los Canales

| Capacidad | Canal HTTP | Canal de consola |
|-----------|------------|------------------|
| Alta persistente de incidente | `POST /api/v1/incidents` → 201 | `create` |
| Auditoría de SLA de un incidente | `GET /api/v1/incidents/{incident_id}/sla` → 200 | `sla` |

- La auditoría acepta el parámetro opcional `reference_time` en ISO 8601 local, sin zona horaria; el alta acepta `created_at` con el mismo formato.
- El alta responde 201 tanto si no hay duplicados como si los hay; un identificador ya existente responde 409.
- La auditoría responde 404 si el incidente no existe.
- Un `reference_time` anterior a `created_at` responde 422 y la consola termina con código de salida 1.
- Una entrada malformada responde 422 y la consola termina con código de salida 2.
- Todo fallo informa un código estable y un mensaje comprensible, sin documento parcial.
- Documento de alta: datos del incidente registrado, `duplicate_group_key`, `is_duplicate` y `duplicate_of`.
- Documento de SLA: `incident_id`, `severity`, `status`, `created_at`, `resolved_at`, `reference_time`, `elapsed_minutes`, `allowed_minutes`, `remaining_minutes`, `is_breached`, `requires_escalation` y la ventana de cómputo aplicada.

### Entidades Clave

- **Incidente registrado**: incidente persistido con identificador, título, texto original, componente, severidad, equipo responsable, estado, instante de creación, instante de resolución cuando exista y clave de grupo de duplicados cuando corresponda; es la unidad que se registra, se consulta y se audita.
- **Aviso de duplicados**: parte de la respuesta de alta compuesta por `is_duplicate`, la lista `duplicate_of` con los identificadores de los equivalentes previos y `duplicate_group_key`.
- **Equivalencia de duplicados**: relación entre dos incidentes activos del mismo componente determinada por la similitud de sus textos originales y por la ventana temporal de la severidad del más antiguo.
- **Grupo de duplicados**: conjunto de incidentes equivalentes encabezado por el original más antiguo; la clave del grupo es su identificador y se hereda cuando el original ya es duplicado.
- **Evaluación de SLA**: resultado determinista para un incidente y un instante de referencia, con minutos consumidos, máximo permitido, minutos restantes, ventana de cómputo, incumplimiento y escalamiento.
- **Política de SLA**: regla vigente por severidad que fija el máximo permitido, la ventana de cómputo y el umbral de escalamiento; es la única fuente de esos valores.
- **Instante de referencia**: momento único contra el que se evalúa el SLA de un incidente; puede ser el actual o uno indicado explícitamente.

## Criterios de Éxito *(obligatorio)*

### Resultados Medibles

- **SC-001**: El 100 % de los registros válidos sigue disponible, con valores idénticos, tras reiniciar el proceso sobre el mismo almacenamiento.
- **SC-002**: El 100 % de los registros con al menos un equivalente previo abierto según la regla vigente devuelve `is_duplicate=true` con `duplicate_of` no vacío en la misma respuesta, y el 0 % de los casos límite (similitud por debajo del umbral, fuera de ventana, otro componente, candidato terminal o sin texto) produce falsos avisos.
- **SC-003**: Para el mismo incidente y el mismo instante de referencia, HTTP y consola coinciden en el 100 % de los campos y valores de SLA, sin discrepancias.
- **SC-004**: Para los mismos datos, `is_duplicate`, `duplicate_of` y `duplicate_group_key` informados por HTTP y consola coinciden en el 100 % de las ejecuciones de comparación.
- **SC-005**: El 100 % de los casos frontera de SLA (límite exacto, un minuto por encima, umbral exacto de escalamiento y semana hábil) produce el resultado esperado, sin diferencias entre canales.
- **SC-006**: Un operador puede registrar un incidente o consultar su SLA en una sola operación por canal, con un tiempo de respuesta percibido por debajo de 1 segundo con 10.000 incidentes activos almacenados.
- **SC-007**: El 100 % de las consultas rechazadas por identificador inexistente, incoherencia temporal o entrada inválida informa un error comprensible y no entrega datos parciales.
- **SC-008**: Ningún aviso de duplicado altera, fusiona ni elimina incidentes: el 100 % de los registros con aviso conserva intactos todos los incidentes previos.
- **SC-009**: El 100 % de los incidentes registrados aparece en el resumen de activos con los mismos datos con los que fue registrado, sin necesidad de intervención manual.
- **SC-010**: En el 100 % de las ejecuciones de dos registros equivalentes concurrentes, ambos incidentes quedan persistidos y la respuesta del segundo informa al primero, sin rechazos por duplicidad.

## Supuestos

- El registro toma el texto original del reporte y deriva de él severidad, componente y equipo con el triaje canónico; no existe sobrescritura manual de la clasificación en esta capacidad.
- El título se deriva del texto original (primera línea recortada, hasta 200 caracteres) cuando el cliente no lo indica.
- El estado inicial es siempre `OPEN`; resolver, cerrar o reabrir incidentes queda fuera del alcance de este hito, aunque la consulta de SLA sí evalúa incidentes terminales ya almacenados.
- La comparación de textos aplica únicamente la conversión a minúsculas; no elimina acentos, signos de puntuación ni espacios, porque la regla vigente no lo contempla.
- La similitud se calcula sobre el texto original completo del nuevo reporte y de cada candidato.
- La ventana temporal aplicable a un par es la de la severidad del incidente más antiguo del par.
- La clave de grupo se hereda cuando el original más antiguo ya pertenece a un grupo; nunca se usa el identificador de un duplicado intermedio como clave.
- Si el nuevo registro resulta ser el más antiguo del conjunto equivalente, él es el original y no hereda clave; no se marca como duplicado, `duplicate_of` queda vacío y las claves de los registros previos no se reescriben.
- Los candidatos sin texto original almacenado no pueden compararse y no generan avisos; es el caso de datos históricos sembrados sin reporte.
- El instante de creación puede indicarse explícitamente para hacer reproducibles las pruebas y las cargas de recuperación; si se omite, se usa el instante de la solicitud.
- Tanto el instante de creación como el de referencia usan fecha y hora locales naive con el mismo formato estricto que la consulta de resumen vigente.
- Los días festivos siguen siendo deuda documentada y no se descuentan del cómputo hábil.
- El almacenamiento es único y compartido por ambos canales; la comprobación de duplicados y el alta se serializan por componente para que dos registros simultáneos equivalentes se avisen entre sí. No hay sincronización entre réplicas ni bloqueo distribuido.
- `duplicate_of` se entrega completo, sin paginación, y contiene sólo identificadores de duplicados previos, porque el aviso debe ser íntegro y accionable.

### Dependencias

- Las reglas canónicas de triaje por impacto, el catálogo cerrado de componentes y equipos y la detección de duplicados del núcleo del dominio.
- La política de SLA vigente por severidad, con sus máximos permitidos, ventanas de cómputo y umbral de escalamiento del 75 %.
- El almacenamiento de incidentes, que ya conserva identificador, título, componente, severidad, estado, instantes y texto original, y que debe admitir la clave de grupo de duplicados.
- El contrato de referencia temporal compartido por los canales y el esquema de códigos estables de la aplicación.
- El resumen de incidentes activos, que debe reflejar los incidentes registrados sin cambios de comportamiento.

### Fuera de Alcance

- Resolver, cerrar, reabrir o reasignar incidentes; el ciclo de vida se limita al alta persistente y a la consulta de SLA.
- Triaje o registro por lote, importaciones masivas y reingesta de históricos.
- Fusión automática, vinculación persistente o reetiquetado de duplicados más allá de la clave de grupo informada.
- Notificaciones externas (correo, mensajería, webhooks) o escalamiento efectivo: el aviso vive en la respuesta del registro.
- Historial de reevaluaciones, instantáneas periódicas de SLA o informes de incumplimiento a lo largo del tiempo; cada consulta evalúa un único instante.
- Calendario de festivos y cómputo de SLA en husos horarios distintos del local.
- Paginación, exportación a archivo y suscripción a cambios.
- Autenticación y autorización específicas para el registro o la consulta.
- Detección de duplicados entre componentes distintos o contra incidentes terminales.
