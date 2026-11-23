# Especificación de Funcionalidad: Resumen de Incidentes Activos

**Rama de la funcionalidad**: rama actual (pendiente de asignación)

**Creado**: 2026-11-22

**Estado**: Borrador

**Entrada**: Descripción del usuario: "Necesitamos consultar el resumen de incidentes actualmente activos (OPEN e IN_PROGRESS) tanto por API HTTP como por CLI, indicando el total activo, cuántos incumplieron su SLA y el detalle de cada incidente (título, componente, severidad, estado, minutos de SLA y si requiere escalamiento), permitiendo filtrar opcionalmente por componente."

## Clarifications

### Session 2026-11-22

- Q: ¿Qué formato debe entregar la consulta del resumen en la consola? → A: Sólo JSON, con la misma estructura y los mismos campos que el canal HTTP.
- Q: ¿Qué deben representar los minutos de SLA que muestra el detalle de cada incidente? → A: Minutos de SLA: 24x7 para P0/P1 y sólo lunes a viernes 08:00-18:00 para P2/P3.
- Q: ¿Qué debe ocurrir si un incidente activo tiene fecha de creación posterior al instante de la consulta? → A: La consulta falla por completo con un error claro, sin totales ni detalle parcial.
- Q: ¿Se puede fijar el instante de consulta desde los canales? → A: Sí, como parámetro opcional; por defecto se usa el instante actual.

## Escenarios de Usuario y Pruebas *(obligatorio)*

### Historia de Usuario 1 - Consultar el resumen de activos por HTTP (Prioridad: P1)

Como persona de guardia o responsable de operaciones, necesito consultar en una sola petición cuántos incidentes están activos, cuántos han incumplido su SLA y el detalle de cada uno, para decidir de inmediato dónde concentrar el trabajo sin revisar la tabla completa.

**Por qué esta prioridad**: es el objetivo central de la funcionalidad; sin los totales y el detalle no hay resumen que consultar y el resto de historias no aporta valor.

**Prueba independiente**: con un conjunto conocido de incidentes activos y terminales, una única consulta HTTP devuelve el total activo, el total incumplido y una entrada de detalle por incidente activo; los terminales no aparecen.

**Escenarios de aceptación**:

1. **Dado** que existen 5 incidentes activos y 3 terminales, **cuando** se consulta el resumen sin filtro, **entonces** el total activo es 5, el detalle contiene exactamente esos 5 incidentes y ninguno de los terminales aparece.
2. **Dado** que existen 4 incidentes activos de los cuales 2 superaron su tiempo permitido, **cuando** se consulta el resumen, **entonces** el total incumplido es 2 y el detalle marca como incumplidos exactamente a esos 2.
3. **Dado** que cada incidente activo tiene título, componente, severidad, estado, minutos de SLA y un indicador de escalamiento, **cuando** se consulta el resumen, **entonces** cada entrada del detalle presenta esos datos completos y consistentes con el incidente almacenado.
4. **Dado** que no existe ningún incidente activo, **cuando** se consulta el resumen, **entonces** la consulta finaliza con éxito, el total activo es 0 y el detalle está vacío.

---

### Historia de Usuario 2 - Obtener el mismo resumen desde la consola (Prioridad: P1)

Como ingeniero de guardia que trabaja por terminal o que automatiza diagnósticos, necesito obtener el mismo resumen desde la consola, con los mismos totales y el mismo detalle que por HTTP, para no cambiar de herramienta ni reinterpretar resultados.

**Por qué esta prioridad**: la funcionalidad se declara explícitamente para ambos canales; un canal con semántica distinta produce decisiones operativas divergentes.

**Prueba independiente**: ejecutando la consulta de consola sobre el mismo conjunto de datos y con el mismo instante de referencia que la consulta HTTP, los totales y los valores del detalle coinciden sin discrepancias.

**Escenarios de aceptación**:

1. **Dado** el mismo conjunto de incidentes y el mismo instante de consulta, **cuando** se solicita el resumen por consola y por HTTP, **entonces** ambos canales devuelven los mismos totales y los mismos valores de detalle.
2. **Dado** que la consulta por consola se ejecuta con éxito, **cuando** el resultado se entrega en la terminal, **entonces** la salida es JSON con los mismos campos y totales que el canal HTTP, legible al imprimirse y consumible por un script.
3. **Dado** un fallo de entrada en la consulta de consola, **cuando** el comando termina, **entonces** informa el problema con un mensaje comprensible y un código de salida distinto de cero, sin imprimir un resumen parcial.

---

### Historia de Usuario 3 - Filtrar el resumen por componente (Prioridad: P2)

Como responsable de un componente específico, necesito limitar el resumen a un solo componente para revisar únicamente los incidentes de mi área y saber cuántos de ellos están incumplidos.

**Por qué esta prioridad**: mejora el enfoque operativo, pero el valor principal ya se entrega con el resumen completo; omitirla no invalida el resto.

**Prueba independiente**: con incidentes activos repartidos en dos componentes, una consulta filtrada por uno de ellos devuelve sólo los incidentes de ese componente y totales coherentes con ese subconjunto, tanto por HTTP como por consola.

**Escenarios de aceptación**:

1. **Dado** que hay incidentes activos en los componentes `payments-gateway` y `auth-identity`, **cuando** se consulta el resumen filtrando por `payments-gateway`, **entonces** el detalle contiene sólo incidentes de `payments-gateway` y los totales corresponden a ese subconjunto.
2. **Dado** un filtro por un componente que no tiene incidentes activos, **cuando** se consulta el resumen, **entonces** la consulta finaliza con éxito, el total activo es 0 y el detalle está vacío.
3. **Dado** un filtro con espacios sobrantes alrededor del nombre del componente, **cuando** se consulta el resumen, **entonces** el resultado es el mismo que sin esos espacios.
4. **Dado** que el filtro se omite o llega vacío, **cuando** se consulta el resumen, **entonces** el resultado incluye todos los incidentes activos sin restricción de componente.

---

### Casos Límite

- **Frontera exacta de incumplimiento**: un incidente con minutos de SLA iguales al máximo permitido no ha incumplido; sólo incumple al superarlo, y el detalle y el total deben reflejar esa misma decisión.
- **Frontera exacta de escalamiento**: un incidente que alcanza exactamente el umbral de escalamiento requiere escalamiento; uno que ya incumplió no se marca como escalamiento pendiente.
- **Incidentes P2 y P3 fuera de horario hábil**: el tiempo transcurrido sólo acumula de lunes a viernes dentro de la ventana hábil; noches, fines de semana y festivos no suman. Un incidente creado el viernes por la tarde y consultado el lunes por la mañana no debe aparecer como incumplido por el fin de semana.
- **Incidente con fecha de creación posterior al instante de consulta**: la consulta completa debe rechazarse con un error definido y sin totales ni detalle parcial; nunca se devuelven minutos negativos ni valores imposibles.
- **Estados terminales con SLA aparentemente vencido**: un incidente resuelto o cerrado nunca aparece en el resumen aunque sus minutos superen el máximo permitido.
- **Todos los activos incumplidos**: el total incumplido puede igualar al total activo y ningún incidente se marca como escalamiento pendiente.
- **Volumen alto**: con al menos 10.000 incidentes activos almacenados, el resumen debe entregarse dentro del tiempo objetivo sin degradar la exactitud de los totales.
- **Títulos con acentos, comillas o caracteres especiales**: el detalle conserva el texto original en ambos canales sin truncamientos ni sustituciones.
- **Consistencia temporal**: todos los incidentes del mismo resumen se evalúan contra un único instante de consulta, sea el actual o uno fijado explícitamente; dos consultas simultáneas no pueden producir minutos incoherentes entre sí.

## Requisitos *(obligatorio)*

### Requisitos Funcionales

- **FR-001**: El sistema DEBE ofrecer el resumen de incidentes activos por HTTP y por consola, con la misma semántica, los mismos campos y la misma información (la igualdad verificable entre canales se fija en FR-015).
- **FR-002**: El sistema DEBE considerar activos únicamente los incidentes en estado `OPEN` o `IN_PROGRESS`, y excluir de forma absoluta los estados terminales `RESOLVED` y `CLOSED`.
- **FR-003**: El resumen DEBE informar el total de incidentes activos incluidos en la respuesta.
- **FR-004**: El resumen DEBE informar cuántos de esos incidentes activos incumplieron su SLA.
- **FR-005**: El detalle DEBE incluir, por cada incidente activo, su identificador, título, componente, severidad, estado, minutos de SLA y si requiere escalamiento.
- **FR-006**: El tiempo transcurrido DEBE expresarse en minutos de SLA consumidos hasta el instante de la consulta: cómputo 24x7 para `P0` y `P1`, y sólo de lunes a viernes dentro de la ventana hábil para `P2` y `P3`, como minutos enteros truncados.
- **FR-007**: Un incidente DEBE considerarse incumplido únicamente cuando sus minutos de SLA superen estrictamente el máximo permitido para su severidad; el límite exacto no es incumplimiento.
- **FR-008**: Un incidente DEBE marcarse como requiere escalamiento cuando está activo, no ha incumplido y sus minutos de SLA alcanzan al menos el 75 % del máximo permitido, redondeado hacia abajo.
- **FR-009**: El resumen DEBE aceptar un filtro opcional por componente que limite tanto el detalle como los totales al subconjunto coincidente.
- **FR-010**: El filtro por componente DEBE compararse exactamente contra el componente registrado, ignorando espacios sobrantes al inicio y al final; un filtro ausente o vacío significa "todos los componentes".
- **FR-011**: Un filtro sin coincidencias DEBE producir una respuesta exitosa con totales en cero y detalle vacío, no un error.
- **FR-012**: El detalle DEBE presentarse en un orden determinista y estable: primero por prioridad de severidad (`P0`, `P1`, `P2`, `P3`), luego por minutos de SLA descendentes y finalmente por identificador ascendente.
- **FR-013**: El resumen DEBE ser una operación de sólo lectura: no modifica incidentes, políticas ni ningún otro dato.
- **FR-014**: El sistema DEBE usar un único instante de consulta para evaluar todos los incidentes de una misma respuesta.
- **FR-015**: Para los mismos datos y el mismo instante, los canales HTTP y consola DEBEN devolver totales idénticos y valores de detalle idénticos.
- **FR-016**: Una consulta con filtro inválido (un componente de más de 128 caracteres, o un valor de tipo incorrecto) DEBE rechazarse con un error de validación claro y un código estable, sin exponer detalles internos ni devolver un resumen parcial.
- **FR-017**: Los umbrales de SLA y la regla de escalamiento aplicados DEBEN ser exactamente los vigentes en el sistema; el resumen no puede introducir valores propios ni versiones paralelas de esas reglas.
- **FR-018**: Un cambio en el origen de los datos de incidentes NO DEBE alterar los totales, el detalle ni el significado de los campos para quien consulta.
- **FR-019**: Si algún incidente activo tiene un instante de creación posterior al instante de consulta, la consulta DEBE rechazarse por completo con un error claro y sin totales ni detalle parcial.
- **FR-020**: Los canales DEBEN aceptar un instante de referencia opcional; si se omite, se usa el instante actual, y si se indica, ese valor DEBE aplicarse de forma única a todos los incidentes, conforme a FR-014, y producir el mismo resultado ante los mismos datos.

### Entidades Clave

- **Incidente activo**: incidente en estado `OPEN` o `IN_PROGRESS` con identificador, título, componente, severidad, instante de creación y, cuando corresponda, instante de resolución; es la unidad que aparece en el detalle.
- **Resumen de activos**: resultado de la consulta compuesto por el total activo, el total incumplido y la lista ordenada de incidentes activos con sus indicadores de SLA y escalamiento.
- **Política de SLA**: regla vigente por severidad que fija el máximo permitido, la ventana de cómputo (24x7 o hábil) y el umbral de escalamiento del 75 %; es la única fuente de esos valores.
- **Filtro por componente**: criterio opcional que restringe la consulta a un componente concreto y que puede estar ausente o vacío.
- **Instante de consulta**: momento único de referencia con el que se calculan los minutos de SLA y los indicadores de todos los incidentes de la respuesta.

## Criterios de Éxito *(obligatorio)*

### Resultados Medibles

- **SC-001**: Un operador obtiene el resumen de una base con 10.000 incidentes activos almacenados en menos de 1 segundo, medido de extremo a extremo en cualquiera de los dos canales.
- **SC-002**: El 100 % de los incidentes activos aparece en el resumen y el 0 % de los terminales aparece, verificado sobre conjuntos con mezclas de estados.
- **SC-003**: Para el mismo conjunto de datos y el mismo instante de consulta, actual o fijado explícitamente, los totales y el detalle de HTTP y consola coinciden en el 100 % de las ejecuciones de comparación, sin discrepancias.
- **SC-004**: El total incumplido coincide exactamente con el número de entradas marcadas como incumplidas en el detalle en el 100 % de las consultas.
- **SC-005**: Los casos frontera de SLA (un minuto antes, exactamente en el límite y un minuto después del máximo permitido) producen el resultado esperado en el 100 % de las comprobaciones, sin diferencias entre los dos canales.
- **SC-006**: Un operador puede restringir el resumen a un componente en una sola consulta o comando, sin filtrar manualmente, en el 100 % de los intentos.
- **SC-007**: El 100 % de las consultas sin coincidencias termina con éxito y muestra totales en cero, sin falsos errores.
- **SC-008**: El 100 % de las consultas rechazadas por entrada inválida o por incoherencia temporal en los datos informa un error comprensible y no entrega datos parciales.

## Supuestos

- El instante de consulta por defecto es el momento de la petición; ambos canales aceptan un instante de referencia explícito para obtener resultados reproducibles, y ese instante es el único que se aplica a todos los incidentes de la respuesta.
- Los totales describen el conjunto devuelto: si se aplica un filtro por componente, los totales corresponden al subconjunto filtrado.
- El tiempo transcurrido se cuenta en minutos de SLA: para `P2` y `P3` sólo cuentan las horas de lunes a viernes dentro de la ventana hábil.
- Los días festivos siguen siendo deuda documentada y no se descuentan del cómputo.
- El componente no se valida contra el catálogo cerrado de equipos: se acepta cualquier componente almacenado y un componente desconocido simplemente no produce coincidencias.
- El detalle se entrega completo, sin paginación ni truncamiento, porque el requisito es el resumen íntegro de los activos.
- Ambos canales entregan JSON con la misma estructura y los mismos campos; la consola no ofrece formatos alternativos.
- La información proviene del almacenamiento de incidentes y de la política de SLA existentes; el único campo añadido al modelo de incidente es el texto original reservado para la detección de duplicados, que esta capacidad no lee ni modifica.
- El resumen no notifica, no escala y no reasigna: sólo informa el indicador de escalamiento.
- El identificador del incidente se incluye en el detalle porque es necesario para correlacionar con el resto de la operación.

### Dependencias

- La política de SLA vigente por severidad, con sus máximos permitidos, ventanas de cómputo y umbral de escalamiento del 75 %.
- El almacenamiento de incidentes existente, que ya registra título, componente, severidad, estado e instantes de creación y resolución.
- El catálogo canónico de estados, que distingue activos (`OPEN`, `IN_PROGRESS`) de terminales (`RESOLVED`, `CLOSED`).
- La definición única de la evaluación de SLA y del indicador de escalamiento, compartida por todos los canales de consulta.

### Fuera de Alcance

- Detección de duplicados y agrupación de incidentes similares; esta capacidad sólo prepara la consulta de candidatos activos del mismo componente, sin comparar textos ni aplicar ventanas.
- Ejecución efectiva de escalamientos, notificaciones o reasignaciones de equipo.
- Paginación, exportación a archivo y suscripción a cambios del resumen.
- Consultas históricas, comparaciones entre varios instantes o rangos de fechas; el resumen se evalúa siempre en un único instante de referencia.
- Cambios en el esquema de datos más allá de la columna reservada para el texto original y del índice necesario para resolver el filtro por componente; sin cambios en el catálogo de severidades ni en la política de SLA.
- Autenticación y autorización específicas para la consulta.
