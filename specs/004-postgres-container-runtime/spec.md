# Especificación de Funcionalidad: Runtime PostgreSQL en contenedores

**Rama de la funcionalidad**: `004-postgres-container-runtime`

**Creado**: 2026-11-23

**Estado**: Borrador

**Entrada**: Descripción del usuario: "Preparar IncidentOps para ejecutarse en contenedores junto con una base de datos relacional dedicada en producción y exponer un chequeo real de salud de conectividad, sin romper el camino local sin infraestructura ni la paridad REST/CLI." Respaldada por: ADR-007 (persistencia dual SQLite/PostgreSQL sin ORM) y ADR-008 (runtime multi-contenedor); Constitución §IV (puertos y composición única) y §V (stack gobernado).

## Clarifications

### Sesión 2026-11-23

- Q: ¿Un único endpoint de salud o separar vida y disponibilidad? → A: un único `GET /health`; 200 sólo si la base responde, 503 si no. No se añaden `/live` ni `/ready` en este hito.
- Q: ¿El proceso debe abortar si la base no responde al arrancar? → A: no. El servicio arranca y reporta 503; Compose evita el arranque prematuro con `depends_on: service_healthy`, y la API se recupera sin reiniciarse cuando la base vuelve.
- Q: ¿Qué ocurre con un motor no admitido en la configuración? → A: error de configuración al componer el repositorio; el proceso no arranca y nunca cae a un almacenamiento local por defecto.
- Q: ¿Qué canal usa la consola cuando la base no responde? → A: escribe el mismo documento JSON en stdout y termina con código 1; el documento es el resultado del comando, no un `problem+json`.
- Q: ¿Se admite el alias `postgres://`? → A: no; sólo `postgresql://`, conforme a ADR-007. Cualquier otro esquema es error de configuración.
- Q: ¿Se migran los datos SQLite existentes? → A: no. No hay herramienta de migraciones en este hito.

## Escenarios de Usuario y Pruebas *(obligatorio)*

### Historia de Usuario 1 - Saber si el servicio puede atender contra su base real (Prioridad: P1)

Como operador de guardia o responsable de despliegue, necesito consultar la salud del servicio y saber si su base de datos dedicada responde de verdad, para decidir si el servicio puede atender o si el problema está en la persistencia.

**Por qué esta prioridad**: es el objetivo central de H004 y la señal que usan tanto una persona como el orquestador de contenedores.

**Prueba independiente**: con la base disponible, la consulta por HTTP y por consola devuelve `connected` y termina en éxito; con la base caída, devuelve `unavailable` y falla de forma explícita, sin traza ni detalles internos.

**Escenarios de aceptación**:

1. **Dado** un servicio en ejecución cuya base de datos configurada responde a una consulta trivial, **cuando** un operador consulta `GET /health`, **entonces** recibe 200 OK con el documento `{"status": "ok", "database": "connected"}`.
2. **Dado** el mismo servicio con la base de datos disponible, **cuando** el operador ejecuta el comando de consola `health`, **entonces** la consola escribe el mismo documento de salud y termina con código de salida 0.
3. **Dado** un servicio en ejecución cuya base de datos no responde, **cuando** un operador consulta `GET /health`, **entonces** recibe 503 Service Unavailable con `{"status": "error", "database": "unavailable"}`, sin traza, credenciales ni detalles internos.
4. **Dado** el mismo servicio con la base de datos no disponible, **cuando** el operador ejecuta `health` en la consola, **entonces** la consola escribe el mismo documento de indisponibilidad y termina con código de salida 1.

**Trazabilidad de pruebas**: E-01 (`tests/test_bdd_h004_salud_runtime.py::test_bdd_e01_el_servicio_confirma_que_su_base_responde`), E-02 (`::test_bdd_e02_la_consola_confirma_la_misma_conectividad`), E-03 (`::test_bdd_e03_una_base_inaccesible_se_informa_como_no_disponible`), E-04 (`::test_bdd_e04_la_consola_informa_la_indisponibilidad`).

---

### Historia de Usuario 2 - Operar el mismo servicio sin infraestructura y con infraestructura (Prioridad: P1)

Como desarrollador, necesito seguir trabajando con almacenamiento local efímero sin contenedores, y como responsable de despliegue necesito el mismo servicio contra una base dedicada, sin que cambien las capacidades ni el contrato de las interfaces.

**Por qué esta prioridad**: el valor de H004 depende de que la ruta local rápida no se pierda y de que el cambio de motor sea transparente.

**Prueba independiente**: la suite completa pasa sin Docker; con el despliegue de referencia, la API arranca ordenada junto a la base, responde sana, conserva datos al recrear la API y sobrevive a una caída y recuperación de la base.

**Escenarios de aceptación**:

1. **Dado** un servicio en ejecución, con la base disponible o no disponible, **cuando** se consulta la salud por HTTP y por consola sobre el mismo estado, **entonces** ambos canales informan exactamente los mismos valores de `status` y `database`.
2. **Dado** un entorno de desarrollo sin base de datos dedicada configurada, **cuando** se arranca el servicio y se consulta su salud, **entonces** informa `connected` usando almacenamiento local efímero, sin exigir contenedores ni credenciales.
3. **Dado** un clon limpio y una sola orden de arranque del despliegue de referencia, **cuando** ambos servicios terminan de iniciar, **entonces** la base queda sana antes que la API, la API queda sana y responde al chequeo de salud sin arranques degradados silenciosos.
4. **Dado** el despliegue de referencia con datos registrados, **cuando** se reinicia la API, se recrea el contenedor de la API o se reinicia la base sin eliminar el volumen, **entonces** los datos se conservan íntegros y consultables.
5. **Dado** el despliegue de referencia con la base detenida, **cuando** la base vuelve a estar disponible, **entonces** la salud informa 200 en pocos segundos sin reiniciar la API y el contenedor vuelve a estar sano sin intervención manual.
6. **Dado** un despliegue con la misma configuración, **cuando** se ejecutan triaje, resumen, alta y SLA por HTTP y por consola, **entonces** los documentos, los valores y los códigos de error son idénticos a los de la ruta local con almacenamiento efímero.

**Trazabilidad de pruebas**: E-05 (`tests/test_bdd_h004_salud_runtime.py::test_bdd_e05_ambos_canales_coinciden_al_informar_la_salud`, parametrizada conectado / no disponible), E-06 (`::test_bdd_e06_el_desarrollo_local_sigue_funcionando_sin_base_dedicada`), C-01 (`tests/adapters/test_factory.py::test_selecciona_adaptador_por_database_url`), C-02 (`tests/contract/test_repository_contract.py`, parametrizado SQLite/PostgreSQL), O-01 (`tools/verify_runtime.py --compose`), O-02 (`tools/verify_runtime.py --compose --resiliencia`).

---

### Casos Límite

- **Base que deja de responder entre peticiones**: cada consulta de salud comprueba la base en ese instante, sin caché; una caída posterior al último chequeo sano se informa como no disponible en la siguiente consulta.
- **Base que deja de responder durante la comprobación**: la espera de la comprobación está acotada y el resultado es `unavailable` dentro del tiempo límite, nunca 500 ni una espera indefinida.
- **Fallo de autenticación o de credenciales**: se informa igual que una caída de conectividad; el documento nunca distingue motor, usuario, host ni causa interna.
- **Arranque con la base caída**: el servicio levanta y responde 503; ninguna operación de negocio se ejecuta contra un esquema no inicializado y el arranque no se bloquea ni se reintenta en bucle infinito.
- **Base que vuelve tras una caída**: la primera consulta de salud posterior informa 200 sin reiniciar el proceso y sin reiniciar el contenedor.
- **Configuración de motor no admitida**: el proceso no arranca, informa un error de configuración comprensible y no abre conexión ni cae a almacenamiento en memoria.
- **Alias de DSN no admitido**: `postgres://…` se rechaza como configuración inválida, igual que cualquier otro esquema distinto de `sqlite://` y `postgresql://`.
- **DSN con credenciales embebidas**: las credenciales entran por entorno y nunca aparecen en documentos de salud, logs, mensajes de error ni en la imagen.
- **Volumen eliminado de forma explícita**: es la única pérdida de datos admitida; `docker compose down` sin `-v` conserva los datos.
- **Base publicada al host**: no se publica por defecto; si el operador decide publicarla, es una decisión explícita fuera del despliegue de referencia.
- **Consola con la base caída**: escribe exactamente el documento de indisponibilidad en stdout y termina con código 1, sin traza, sin mensaje adicional y sin `problem+json`.
- **Salida estándar contaminada**: el documento de salud es el único resultado del comando, de modo que un script pueda consumirlo sin filtrar líneas.
- **Healthcheck del contenedor**: usa el mismo `/health`, por lo que un 503 también marca el contenedor como no sano y evita declararlo listo antes de tiempo.
- **Cliente o intermediario con respuestas viejas**: el chequeo de salud no se cachea ni en el servidor ni en intermediarios.
- **Reinicio de la base con la API activa**: la API no pierde configuración ni estado en memoria relevante; al volver la base, el servicio se recupera solo.

## Requisitos *(obligatorio)*

### Requisitos Funcionales

- **FR-001**: El servicio DEBE exponer `GET /health` y ejecutar una comprobación real de conectividad con la base configurada en cada petición; cuando la base responde, DEBE responder 200 OK con exactamente `{"status": "ok", "database": "connected"}`.
- **FR-002**: Cuando la comprobación falla, `GET /health` DEBE responder 503 Service Unavailable con exactamente `{"status": "error", "database": "unavailable"}`; NUNCA 500, traza, credenciales ni detalles del motor.
- **FR-003**: La consola DEBE ofrecer el comando `health`, que escribe en la salida estándar el mismo documento que `GET /health` y termina con código de salida 0 si está conectado o 1 si no lo está, sin depender del adaptador HTTP.
- **FR-004**: La comprobación de salud DEBE exponerse como caso de uso en la capa de aplicación y delegar en el puerto de repositorio; el servicio NO DEBE contener SQL, códigos HTTP ni detalles de motor.
- **FR-005**: El puerto de repositorio DEBE mantener `check_health() -> bool`, sin lanzar excepciones: sólo devuelve `True` si una consulta trivial obtiene fila, y `False` ante cualquier fallo de conectividad, autenticación o tiempo de espera.
- **FR-006**: La fábrica de salida DEBE seleccionar el repositorio exclusivamente por `DATABASE_URL`: ausente o `sqlite:///:memory:` → SQLite en memoria; `sqlite:///ruta` → SQLite en archivo; `postgresql://…` → PostgreSQL; cualquier otro esquema → `ConfigurationError` antes de abrir conexión, sin fallback silencioso.
- **FR-007**: Ningún adaptador de entrada DEBE leer `DATABASE_URL` ni instanciar un repositorio concreto; la fábrica es el único punto que interpreta el DSN.
- **FR-008**: El adaptador PostgreSQL DEBE implementar el puerto completo con semántica equivalente a SQLite: `INSERT` estricto, conflicto de identificador traducido al mismo error de aplicación, columnas explícitas, filtro de activos y sin cálculo de SLA, similitud, claves de grupo ni ordenación.
- **FR-009**: El esquema PostgreSQL DEBE crearse de forma idempotente con las mismas tablas, columnas e índices compuestos; `created_at` y `resolved_at` DEBEN persistirse como texto naive ISO 8601 con microsegundos y NUNCA como `TIMESTAMP`, `TIMESTAMPTZ`, época numérica ni `now()` del motor.
- **FR-010**: Un fallo de conectividad al arrancar NUNCA DEBE impedir que el servicio se levante y reporte 503; la recuperación de la base DEBE devolver 200 sin reiniciar la API.
- **FR-011**: La inicialización del esquema DEBE ser idempotente y reintentarse tras una caída; ninguna operación de negocio DEBE ejecutarse contra un esquema no inicializado.
- **FR-012**: Las capacidades de triaje, resumen, alta y SLA DEBEN conservar exactamente su comportamiento, contratos y códigos de error con ambos motores; la paridad se demuestra con la misma suite de contrato.
- **FR-013**: La imagen de la API DEBE construirse desde el repositorio y `uv.lock` con `uv`, ejecutarse como usuario sin privilegios, servir con Uvicorn sobre FastAPI y no contener credenciales, DSN ni estado persistente.
- **FR-014**: `docker-compose.yml` DEBE definir dos servicios: `db` con `postgres:16-alpine`, volumen nombrado para `PGDATA` y healthcheck con `pg_isready`; y `api` con `DATABASE_URL` apuntando a `db`, `depends_on` con `service_healthy`, healthcheck sobre `/health` y una sola réplica.
- **FR-015**: La base NO DEBE publicarse al host por defecto; las credenciales DEBEN entrar por entorno, no versionarse y documentarse mediante un `.env.example` con marcadores, con `.env` ignorado por Git.
- **FR-016**: `.dockerignore` DEBE excluir secretos, metadatos de Git, entornos virtuales, cachés, bases locales y artefactos de desarrollo para que la imagen sea mínima y reproducible.
- **FR-017**: La documentación operativa DEBE describir el arranque, la parada, la persistencia del volumen, el diagnóstico de salud y las variables de entorno necesarias.

### Requisitos No Funcionales

- **RNF-001 (aislamiento de pruebas)**: los escenarios BDD DEBEN usar dobles en memoria y ejecutarse sin Docker, sin red y sin base real; la integración PostgreSQL DEBE vivir en una suite separada.
- **RNF-002 (latencia)**: con la base sana, el p95 de `/health` DEBE ser ≤ 200 ms en local; con la base caída, la respuesta 503 DEBE llegar en ≤ 3 s, con un tiempo de espera de comprobación ≤ 2 s.
- **RNF-003 (arranque reproducible)**: desde un clon limpio, `docker compose up --build` DEBE dejar ambos servicios sanos en ≤ 60 s la primera vez y ≤ 20 s en arranques posteriores, en un host de desarrollo estándar.
- **RNF-004 (persistencia)**: los datos DEBEN sobrevivir a `docker compose restart`, a `docker compose up --force-recreate api` y a `docker compose down` sin `-v`; sólo la eliminación explícita del volumen los pierde.
- **RNF-005 (recuperación)**: tras volver la base, `/health` DEBE reportar 200 en ≤ 5 s sin reiniciar la API, y el contenedor `api` DEBE volver a `healthy` sin intervención manual.
- **RNF-006 (paridad de motores)**: la misma suite de contrato DEBE pasar en SQLite y PostgreSQL con cero divergencias de valores, errores y orden; el benchmark de 10 000 incidentes DEBE conservar los objetivos de SC-006 de H003.
- **RNF-007 (imagen)**: `python:3.12-slim`, multietapa, sin cadena de compilación en runtime, usuario no root, dependencias fijadas por `uv.lock` e imagen resultante ≤ 400 MB.
- **RNF-008 (seguridad)**: ni la imagen ni el repositorio DEBEN contener credenciales o DSN reales; `/health` no DEBE exponer motor, host, usuario ni mensajes del driver; la base no DEBE ser alcanzable desde el host por defecto.
- **RNF-009 (fronteras hexagonales)**: `uv run ruff check src/` DEBE pasar; `psycopg` sólo puede importarse desde `src/adapters/outbound/`; `DATABASE_URL` sólo puede leerse en la fábrica; dominio y aplicación no cambian de dependencias.
- **RNF-010 (compatibilidad)**: el desarrollo local con Python ≥ 3.10 DEBE seguir funcionando; la única dependencia nueva es `psycopg[binary]`, sin ORM ni herramienta de migraciones.
- **RNF-011 (portabilidad)**: el despliegue DEBE funcionar con una sola orden en Windows, macOS y Linux con Docker, sin rutas absolutas del host ni pasos manuales específicos.
- **RNF-012 (observabilidad mínima)**: los logs no DEBEN incluir el DSN ni credenciales; el documento de salud DEBE ser estable y consumible por scripts y por el healthcheck del contenedor.
- **RNF-013 (CI)**: `uv run pytest` DEBE pasar sin Docker; la verificación de integración con PostgreSQL y `uv run ruff check src/` DEBEN ejecutarse en el pipeline cuando haya motor disponible.

### Interfaces de los Canales

| Capacidad | Canal HTTP | Canal de consola |
|-----------|------------|------------------|
| Salud del servicio | `GET /health` → 200 / 503 | `health` → salida 0 / 1 |

| Estado | HTTP | Cuerpo exacto | Consola | Salida |
|--------|------|---------------|---------|--------|
| Conectado | 200 | `{"status": "ok", "database": "connected"}` | mismo JSON en stdout | 0 |
| No disponible | 503 | `{"status": "error", "database": "unavailable"}` | mismo JSON en stdout | 1 |

- `Content-Type: application/json` en ambos estados; `Cache-Control: no-store` para que ningún intermediario reutilice un resultado viejo.
- La consola no imprime traza ni mensaje adicional; el documento es el resultado.

### Entidades Clave

- **Estado de salud**: resultado de evaluar una sola vez la conectividad con la base, compuesto por `status` (`ok` o `error`) y `database` (`connected` o `unavailable`); es la unidad que comparten HTTP y consola.
- **Comprobación de conectividad**: consulta trivial contra el almacenamiento configurado que responde con un booleano y no propaga fallos.
- **DSN de configuración**: cadena de conexión que determina el motor y se interpreta en un único punto; nunca define comportamiento de negocio.
- **Motor de persistencia**: implementación intercambiable del mismo puerto de repositorio, con igual semántica de escritura, lectura y errores.
- **Incidente**: entidad de negocio ya definida en H003; H004 no la modifica, sólo la persiste en un motor adicional.
- **Despliegue de referencia**: conjunto de servicios de API y base que se levanta de forma ordenada, con volumen durable y chequeos de salud.

## Criterios de Éxito *(obligatorio)*

### Resultados Medibles

- **SC-001**: El 100 % de las consultas de salud informa `connected` si y sólo si la base responde en ese instante, sin caché ni valores obsoletos.
- **SC-002**: El 100 % de las comprobaciones con la base caída responde 503 y nunca 500, dentro del tiempo límite.
- **SC-003**: HTTP y consola coinciden en el 100 % de los campos y valores del documento de salud, en ambos estados.
- **SC-004**: Desde un clon limpio, una sola orden deja el despliegue de referencia sano, con la API esperando a la base y sin arranques degradados silenciosos.
- **SC-005**: El 100 % de los datos sobrevive a recrear o reiniciar la API y a reiniciar la base; sólo se pierden al eliminar el volumen de forma explícita.
- **SC-006**: La suite de contrato pasa en ambos motores con cero divergencias y el comportamiento de triaje, resumen, alta y SLA no cambia.
- **SC-007**: El 100 % de las configuraciones de motor no admitidas falla de forma explícita y comprensible, sin abrir conexión ni caer a memoria.
- **SC-008**: El 100 % de la suite se ejecuta sin Docker ni credenciales, y la integración con PostgreSQL se ejecuta cuando el motor está disponible.

## Supuestos

- Un solo host, una sola réplica de API y cerrojo por componente de proceso (ADR-006/007); escalar exige otro ADR.
- `postgres:16-alpine` y `python:3.12-slim` son las versiones fijadas del hito.
- No hay migración de datos SQLite existentes ni herramienta de migraciones de esquema.
- No hay autenticación en `/health`; no expone datos de negocio.
- El healthcheck del contenedor `api` usa el propio `/health`, de modo que 503 también marca el contenedor como no sano.
- La API puede arrancar antes de que el esquema exista; la primera operación de negocio lo inicializa de forma idempotente.
- La ruta local sin `DATABASE_URL` sigue siendo el camino por defecto para desarrollo y pruebas; el almacenamiento en memoria es efímero por definición.
- El operador que necesite inspeccionar la base desde el host lo hace de forma explícita; no forma parte del despliegue de referencia.

### Dependencias

- ADR-007: adaptador PostgreSQL dedicado con `psycopg[binary]`, sin ORM.
- ADR-008: topología `api` + `db` con Compose, volumen nombrado y healthchecks.
- Constitución §IV y §V; `IncidentRepositoryPort`, `ClockPort` y la fábrica única.
- Contratos de triaje, resumen, alta y SLA de H001–H003 sin cambios.

### Fuera de Alcance

- Alta disponibilidad, TLS, orquestación multi-host, copias de seguridad automáticas y gestión centralizada de secretos.
- Bloqueo distribuido, varias réplicas de API, pooler de conexiones y réplica de lectura.
- Migraciones versionadas, Alembic, ORM o cambios de esquema automáticos.
- Endpoints `/live` y `/ready` separados, métricas, trazas o paneles.
- Migración de datos históricos de SQLite a PostgreSQL.
