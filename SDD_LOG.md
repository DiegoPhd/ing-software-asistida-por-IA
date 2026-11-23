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
    - **C1 (CRITICAL)**: la siembra ON CONFLICT DO UPDATE de sla_policies choca con la prohibición textual de UPSERT/ON CONFLICT DO UPDATE en el contrato de persistencia (§Contrato de persistencia, :265-267). El plan la reinterpreta en lugar de enmendar la Constitución. Es el único bloqueo constitucional.
    - **I5 (MEDIUM)**: la validación de invariantes replicada en el adaptador PostgreSQL roza el Principio I (reglas únicas en src/domain/), aunque sigue el precedente aceptado de H003 y ADR-004 §4; conviene documentarlo o centralizarlo.
    - **Antes**: - **RNF-003 (arranque reproducible)**: desde un clon limpio, `docker compose up --build` DEBE dejar ambos servicios sanos en ≤ 60 s la primera vez y ≤ 20 s en arranques posteriores, en un host de desarrollo estándar.
    **Después**: - **RNF-003 (arranque reproducible)**: desde un clon limpio y con las imágenes base ya descargadas, `docker compose up --build` DEBE dejar ambos servicios sanos en ≤ 60 s la primera vez y ≤ 20 s en arranques posteriores, medidos en el runner de CI de referencia (4 vCPU, 8 GB RAM, SSD y red local). La descarga inicial de imágenes se mide aparte y no cuenta para el umbral.
    - **Antes**: - **RNF-011 (portabilidad)**: el despliegue DEBE funcionar con una sola orden en Windows, macOS y Linux con Docker, sin rutas absolutas del host ni pasos manuales específicos.
    **Después**: - **RNF-011 (portabilidad)**: el despliegue DEBE funcionar con una sola orden en Windows 11, macOS 14 y Ubuntu 22.04 con Docker Compose v2, sin rutas absolutas del host ni pasos manuales específicos. La verificación automatizada cubre Ubuntu en CI; Windows y macOS se validan con `quickstart.md` antes de cerrar el hito.
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

- **Diferencia entre *Commands* (`/speckit.*`) y *Agent Skills* (`hexagonal-architecture`, `bdd-acceptance`, `adr-writer`)**: Explica cómo OpenCode carga las *skills* bajo demanda y por qué fue necesario seguir el orden causal ADR $\rightarrow$ Constitución $\rightarrow$ Hito tanto en clase (`ADR-003` antes de `docs/constitution.md`) como en el Reto 2 (`ADR-009` y actualización de `.specify/memory/constitution.md` antes de especificar e implementar el Hito `004`).
    - OpenCode primerametnte revisar en diferentes directorios (`~/.config/opencode/skills`, `.opencode/skills`) las skills que tenga disponible en el proyecto, luego el usuario invoca la skill asociada, ya sea con una instrucción o simplemente con `@skill-id` enseguida se empiezan a ejecutar de forma ordenada las instrucciones de la skill.
    - Fue necesario por el nivel de los archivos, vamos de más alto nivel (ADR) a más bajo nivel (Hito), así, el ADR continente la decisión estructural, con alternativas y consecuencias, luego en la constitución se usa el ADR para tomar decisiones y finalmente el Hito lee la constitución para las específicaciones, el pla y las tareas.
- **Valor de la Arquitectura Hexagonal**: Explica cómo compartir `IncidentService` e `IncidentRepositoryPort` facilitó exponer FastAPI, Typer y el adaptador PostgreSQL sin tocar el dominio (y cómo prepara la incorporación de futuros adaptadores).
    - En este caso `IncidentService` tiene 5 capacidades (triage, summary, create, sla y health), y depende del protocolo de `IncidentRepositoryPort`. Las 5 capacidades junto con FastAPI y Typer comparten  un método de servicio, haciendo que solo haya una sola lógica.
    Esto además prepara la implementación a futuros adaptadores porque simplemente es implementar el protocolo y ampliar el suite de contrato.

- **Uso intencional de *Reasoning / Extended Thinking* en OpenCode**: ¿En qué comandos (`/speckit.clarify`, `/speckit.plan`, `/speckit.analyze`) aportó mayor valor el razonamiento extendido y en cuáles (`/speckit.implement`) resultó más eficiente un modelo rápido?
    - En este caso no aplica, dado que siempre utilicé el mismo modelo con el mismo esfuerzo el cual fue DeepSeek V4.1 Flash con esfuerzo en High
---

## 4. Evidencia de Verificación Determinista

- **Análisis estático de fronteras hexagonales (`uv run ruff check src/`)**:

```text
All checks passed!
```

- **Salida completa de `uv run pytest -v`**:

```text
platform win32 -- Python 3.10.2, pytest-9.2.0, pluggy-1.7.0 -- D:\Educación\Otros Estudios\Ingeniería de sotfware\starter-project\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: D:\Educación\Otros Estudios\Ingeniería de sotfware\starter-project
configfile: pyproject.toml
testpaths: tests
plugins: anyio-4.16.0
collected 303 items                                                                                                                                                                        

tests/adapters/test_api.py::test_caida_critica_devuelve_p0 PASSED                                                                                                                    [  0%]
tests/adapters/test_api.py::test_cuenta_bloqueada_no_es_p0 PASSED                                                                                                                    [  0%]
tests/adapters/test_api.py::test_texto_en_blanco_devuelve_422 PASSED                                                                                                                 [  0%]
tests/adapters/test_api.py::test_identificador_vacio_devuelve_422 PASSED                                                                                                             [  1%]
tests/adapters/test_api.py::test_campo_faltante_devuelve_422_con_codigo_estable PASSED                                                                                               [  1%]
tests/adapters/test_api.py::test_health_responde_ok PASSED                                                                                                                           [  1%]
tests/adapters/test_api.py::test_alta_devuelve_201_con_el_documento_canonico PASSED                                                                                                  [  2%]
tests/adapters/test_api.py::test_la_auditoria_devuelve_200_con_el_documento_canonico PASSED                                                                                          [  2%]
tests/adapters/test_api.py::test_rutas_ajenas_al_contrato_responden_problem_json PASSED                                                                                              [  2%]
tests/adapters/test_api.py::test_campo_desconocido_en_el_cuerpo_es_422 PASSED                                                                                                        [  3%]
tests/adapters/test_api.py::test_created_at_con_tipo_incorrecto_es_create_creacion_invalida PASSED                                                                                   [  3%]
tests/adapters/test_api.py::test_parametro_desconocido_en_el_alta_es_422 PASSED                                                                                                      [  3%]
tests/adapters/test_api.py::test_parametros_invalidos_en_la_auditoria_son_422[parametros0] PASSED                                                                                    [  4%]
tests/adapters/test_api.py::test_parametros_invalidos_en_la_auditoria_son_422[parametros1] PASSED                                                                                    [  4%]
tests/adapters/test_api.py::test_identificador_solo_espacios_en_la_auditoria_es_422 PASSED                                                                                           [  4%]
tests/adapters/test_api.py::test_datos_incoherentes_responden_409_sla_datos_inconsistentes PASSED                                                                                    [  5%]
tests/adapters/test_api.py::test_el_conflicto_de_alta_es_409_create_id_conflicto PASSED                                                                                              [  5%]
tests/adapters/test_api.py::test_el_motor_caido_conserva_el_error_generico_de_negocio PASSED                                                                                         [  5%]
tests/adapters/test_cli.py::test_triaje_en_linea_devuelve_json PASSED                                                                                                                [  6%]
tests/adapters/test_cli.py::test_triaje_desde_stdin PASSED                                                                                                                           [  6%]
tests/adapters/test_cli.py::test_triaje_desde_archivo PASSED                                                                                                                         [  6%]
tests/adapters/test_cli.py::test_texto_en_blanco_sale_con_codigo_2 PASSED                                                                                                            [  7%]
tests/adapters/test_cli.py::test_identificador_ausente_sale_con_codigo_2 PASSED                                                                                                      [  7%]
tests/adapters/test_cli.py::test_fuentes_de_texto_ambiguas_salen_con_codigo_2 PASSED                                                                                                 [  7%]
tests/adapters/test_cli.py::test_archivo_con_lista_sale_con_codigo_2 PASSED                                                                                                          [  8%]
tests/adapters/test_cli.py::test_identificador_en_conflicto_sale_con_codigo_2 PASSED                                                                                                 [  8%]
tests/adapters/test_cli.py::test_archivo_inexistente_sale_con_codigo_2 PASSED                                                                                                        [  8%]
tests/adapters/test_cli.py::test_create_sale_con_cero_y_documento_json PASSED                                                                                                        [  9%]
tests/adapters/test_cli.py::test_create_con_fecha_invalida_sale_con_2[2026-11-20 10:00:00] PASSED                                                                                    [  9%]
tests/adapters/test_cli.py::test_create_con_fecha_invalida_sale_con_2[2026-11-20T10:00:00+00:00] PASSED                                                                              [  9%]
tests/adapters/test_cli.py::test_create_con_identificador_repetido_sale_con_1 PASSED                                                                                                 [ 10%]
tests/adapters/test_cli.py::test_sla_sale_con_cero_y_documento_json PASSED                                                                                                           [ 10%]
tests/adapters/test_cli.py::test_sla_con_identificador_vacio_sale_con_2 PASSED                                                                                                       [ 10%]
tests/adapters/test_cli.py::test_sla_inexistente_sale_con_1 PASSED                                                                                                                   [ 11%]
tests/adapters/test_cli.py::test_sla_con_fecha_invalida_sale_con_2 PASSED                                                                                                            [ 11%]
tests/adapters/test_factory.py::test_selecciona_adaptador_por_database_url PASSED                                                                                                    [ 11%]
tests/adapters/test_factory.py::test_ambos_adaptadores_cumplen_el_puerto PASSED                                                                                                      [ 12%]
tests/adapters/test_factory.py::test_construir_postgres_no_exige_un_servidor_vivo PASSED                                                                                             [ 12%]
tests/adapters/test_factory.py::test_la_fabrica_inyecta_el_reloj_y_el_repositorio PASSED                                                                                             [ 12%]
tests/adapters/test_factory.py::test_la_configuracion_no_admitida_falla_sin_abrir_conexion[mysql://localhost/incidentops] PASSED                                                     [ 13%]
tests/adapters/test_factory.py::test_la_configuracion_no_admitida_falla_sin_abrir_conexion[sqlite://] PASSED                                                                         [ 13%]
tests/adapters/test_factory.py::test_la_configuracion_no_admitida_falla_sin_abrir_conexion[sqlite:///] PASSED                                                                        [ 13%]
tests/adapters/test_factory.py::test_la_configuracion_no_admitida_falla_sin_abrir_conexion[postgres://localhost/incidentops] PASSED                                                  [ 14%]
tests/adapters/test_factory.py::test_la_configuracion_no_admitida_falla_sin_abrir_conexion[postgresql://] PASSED                                                                     [ 14%]
tests/adapters/test_factory.py::test_la_configuracion_no_admitida_falla_sin_abrir_conexion[] PASSED                                                                                  [ 14%]
tests/adapters/test_factory.py::test_la_configuracion_no_admitida_falla_sin_abrir_conexion[   ] PASSED                                                                               [ 15%]
tests/adapters/test_factory.py::test_el_error_de_configuracion_solo_cita_el_esquema PASSED                                                                                           [ 15%]
tests/adapters/test_factory.py::test_la_variable_ausente_usa_memoria PASSED                                                                                                          [ 15%]
tests/adapters/test_factory.py::test_la_variable_vacia_es_configuracion_invalida PASSED                                                                                              [ 16%]
tests/adapters/test_factory.py::test_la_variable_postgresql_selecciona_postgres PASSED                                                                                               [ 16%]
tests/adapters/test_factory.py::test_resolve_database_path_conserva_las_rutas_sqlite PASSED                                                                                          [ 16%]
tests/adapters/test_postgres_repository.py::test_la_salud_es_verdadera_solo_si_hay_fila PASSED                                                                                       [ 17%]
tests/adapters/test_postgres_repository.py::test_la_salud_informa_falso_ante_error_de_conexion PASSED                                                                                [ 17%]
tests/adapters/test_postgres_repository.py::test_la_salud_no_espera_mas_que_el_plazo PASSED                                                                                          [ 17%]
tests/adapters/test_sqlite_repository.py::test_el_repositorio_cumple_el_puerto_por_firma PASSED                                                                                      [ 18%]
tests/adapters/test_sqlite_repository.py::test_el_resumen_emite_una_sola_consulta_sin_n_mas_uno PASSED                                                                               [ 18%]
tests/adapters/test_sqlite_repository.py::test_el_filtro_por_componente_usa_el_indice_compuesto PASSED                                                                               [ 18%]
tests/adapters/test_sqlite_repository.py::test_migra_raw_text_en_bases_heredadas PASSED                                                                                              [ 19%]
tests/adapters/test_sqlite_repository.py::test_rechaza_database_url_con_esquema_no_soportado[mysql] PASSED                                                                           [ 19%]
tests/adapters/test_sqlite_repository.py::test_rechaza_database_url_con_esquema_no_soportado[sqlite-sin-ruta] PASSED                                                                 [ 19%]
tests/adapters/test_sqlite_repository.py::test_rechaza_database_url_con_esquema_no_soportado[sqlite-sin-archivo] PASSED                                                              [ 20%]
tests/adapters/test_sqlite_repository.py::test_rechaza_database_url_con_esquema_no_soportado[alias-postgres] PASSED                                                                  [ 20%]
tests/adapters/test_sqlite_repository.py::test_rechaza_database_url_con_esquema_no_soportado[vacia] PASSED                                                                           [ 20%]
tests/adapters/test_sqlite_repository.py::test_rechaza_database_url_con_esquema_no_soportado[solo-espacios] PASSED                                                                   [ 21%]
tests/adapters/test_sqlite_repository.py::test_resuelve_memoria_y_archivo PASSED                                                                                                     [ 21%]
tests/adapters/test_sqlite_repository.py::test_la_url_vacia_es_configuracion_invalida PASSED                                                                                         [ 21%]
tests/adapters/test_sqlite_repository.py::test_rechaza_identificador_o_componente_vacios[incidente0-incident_id] PASSED                                                              [ 22%]
tests/adapters/test_sqlite_repository.py::test_rechaza_identificador_o_componente_vacios[incidente1-component] PASSED                                                                [ 22%]
tests/adapters/test_sqlite_repository.py::test_rechaza_terminal_sin_resolved_at[RESOLVED] PASSED                                                                                     [ 22%]
tests/adapters/test_sqlite_repository.py::test_rechaza_terminal_sin_resolved_at[CLOSED] PASSED                                                                                       [ 23%]
tests/adapters/test_sqlite_repository.py::test_rechaza_fechas_con_zona_horaria PASSED                                                                                                [ 23%]
tests/adapters/test_sqlite_repository.py::test_el_resumen_no_modifica_datos PASSED                                                                                                   [ 23%]
tests/adapters/test_sqlite_repository.py::test_el_resumen_es_equivalente_entre_adaptador_y_doble PASSED                                                                              [ 24%]
tests/adapters/test_sqlite_repository.py::test_consulta_puntual_y_candidatos_de_duplicados PASSED                                                                                    [ 24%]
tests/adapters/test_sqlite_repository.py::test_ida_y_vuelta_de_equipo_y_clave_de_grupo PASSED                                                                                        [ 24%]
tests/adapters/test_sqlite_repository.py::test_migra_columnas_nuevas_en_bases_de_h002 PASSED                                                                                         [ 25%]
tests/adapters/test_sqlite_repository.py::test_save_incident_rechaza_el_conflicto_sin_sobrescribir PASSED                                                                            [ 25%]
tests/adapters/test_sqlite_repository.py::test_la_siembra_sintetica_es_idempotente PASSED                                                                                            [ 25%]
tests/adapters/test_sqlite_repository.py::test_get_incident_mapea_terminales_y_sus_columnas PASSED                                                                                   [ 26%]
tests/adapters/test_sqlite_repository.py::test_get_incident_rechaza_datos_incoherentes[severity] PASSED                                                                              [ 26%]
tests/adapters/test_sqlite_repository.py::test_get_incident_rechaza_datos_incoherentes[status] PASSED                                                                                [ 26%]
tests/adapters/test_sqlite_repository.py::test_get_incident_rechaza_datos_incoherentes[recommended_team] PASSED                                                                      [ 27%]
tests/adapters/test_sqlite_repository.py::test_get_incident_rechaza_datos_incoherentes[created_at] PASSED                                                                            [ 27%]
tests/adapters/test_sqlite_repository.py::test_rechaza_equipo_fuera_del_catalogo_al_escribir PASSED                                                                                  [ 27%]
tests/adapters/test_sqlite_repository.py::test_las_fechas_nuevas_se_persisten_con_microsegundos PASSED                                                                               [ 28%]
tests/adapters/test_sqlite_repository.py::test_el_plan_de_la_clave_de_grupo_usa_el_indice_nuevo PASSED                                                                               [ 28%]
tests/adapters/test_sqlite_repository.py::test_el_dominio_ordena_lo_que_el_adaptador_no_ordena PASSED                                                                                [ 28%]
tests/application/test_services.py::test_triaje_valido_delega_en_el_dominio PASSED                                                                                                   [ 29%]
tests/application/test_services.py::test_texto_vacio_es_rechazado PASSED                                                                                                             [ 29%]
tests/application/test_services.py::test_identificador_vacio_es_rechazado PASSED                                                                                                     [ 29%]
tests/application/test_services.py::test_identificador_demasiado_largo_es_rechazado PASSED                                                                                           [ 30%]
tests/application/test_services.py::test_texto_demasiado_largo_es_rechazado PASSED                                                                                                   [ 30%]
tests/application/test_services.py::test_texto_con_espacios_alrededor_es_valido PASSED                                                                                               [ 30%]
tests/application/test_services.py::test_el_alta_clasifica_persiste_y_lee_el_reloj_una_sola_vez PASSED                                                                               [ 31%]
tests/application/test_services.py::test_el_titulo_se_deriva_de_la_primera_linea_sin_superar_200 PASSED                                                                              [ 31%]
tests/application/test_services.py::test_el_titulo_indicado_se_recorta_y_se_valida PASSED                                                                                            [ 31%]
tests/application/test_services.py::test_el_texto_se_persiste_sin_normalizar PASSED                                                                                                  [ 32%]
tests/application/test_services.py::test_created_at_explicito_no_lee_el_reloj PASSED                                                                                                 [ 32%]
tests/application/test_services.py::test_el_conflicto_del_puerto_se_propaga_sin_sobrescribir PASSED                                                                                  [ 32%]
tests/application/test_services.py::test_el_alta_rechaza_entradas_invalidas_sin_persistir[kwargs0-CREATE_ID_VACIO-incident_id] PASSED                                                [ 33%]
tests/application/test_services.py::test_el_alta_rechaza_entradas_invalidas_sin_persistir[kwargs1-CREATE_ID_DEMASIADO_LARGO-incident_id] PASSED                                      [ 33%]
tests/application/test_services.py::test_el_alta_rechaza_entradas_invalidas_sin_persistir[kwargs2-CREATE_TEXTO_VACIO-raw_text] PASSED                                                [ 33%]
tests/application/test_services.py::test_el_alta_rechaza_entradas_invalidas_sin_persistir[kwargs3-CREATE_TEXTO_DEMASIADO_LARGO-raw_text] PASSED                                      [ 33%]
tests/application/test_services.py::test_el_alta_rechaza_entradas_invalidas_sin_persistir[kwargs4-CREATE_TITULO_VACIO-title] PASSED                                                  [ 34%]
tests/application/test_services.py::test_el_alta_rechaza_entradas_invalidas_sin_persistir[kwargs5-CREATE_TITULO_DEMASIADO_LARGO-title] PASSED                                        [ 34%]
tests/application/test_services.py::test_el_alta_rechaza_entradas_invalidas_sin_persistir[kwargs6-CREATE_CREACION_INVALIDA-created_at] PASSED                                        [ 34%]
tests/application/test_services.py::test_el_alta_informa_el_duplicado_y_persiste_la_clave PASSED                                                                                     [ 35%]
tests/application/test_services.py::test_la_auditoria_devuelve_contexto_y_lee_el_reloj_una_sola_vez PASSED                                                                           [ 35%]
tests/application/test_services.py::test_la_auditoria_es_de_solo_lectura PASSED                                                                                                      [ 35%]
tests/application/test_services.py::test_identificador_inexistente_es_no_encontrado PASSED                                                                                           [ 36%]
tests/application/test_services.py::test_identificador_vacio_es_entrada_invalida PASSED                                                                                              [ 36%]
tests/application/test_services.py::test_referencia_aware_es_entrada_invalida PASSED                                                                                                 [ 36%]
tests/application/test_services.py::test_referencia_anterior_a_la_creacion_es_422 PASSED                                                                                             [ 37%]
tests/application/test_services.py::test_datos_incoherentes_son_409[incidente0] PASSED                                                                                               [ 37%]
tests/application/test_services.py::test_datos_incoherentes_son_409[incidente1] PASSED                                                                                               [ 37%]
tests/application/test_services.py::test_datos_incoherentes_son_409[incidente2] PASSED                                                                                               [ 38%]
tests/application/test_services.py::test_el_caso_de_uso_de_salud_delega_en_el_puerto[True] PASSED                                                                                    [ 38%]
tests/application/test_services.py::test_el_caso_de_uso_de_salud_delega_en_el_puerto[False] PASSED                                                                                   [ 38%]
tests/contract/test_repository_contract.py::test_los_cinco_metodos_del_puerto_responden[sqlite] PASSED                                                                               [ 39%]
tests/contract/test_repository_contract.py::test_los_cinco_metodos_del_puerto_responden[postgresql] SKIPPED (TEST_POSTGRES_URL no definida: se omite PostgreSQL)                     [ 39%]
tests/contract/test_repository_contract.py::test_conflicto_estricto_sin_sobrescribir[sqlite] PASSED                                                                                  [ 39%]
tests/contract/test_repository_contract.py::test_conflicto_estricto_sin_sobrescribir[postgresql] SKIPPED (TEST_POSTGRES_URL no definida: se omite PostgreSQL)                        [ 40%]
tests/contract/test_repository_contract.py::test_lista_solo_activos_y_filtra_por_componente[sqlite] PASSED                                                                           [ 40%]
tests/contract/test_repository_contract.py::test_lista_solo_activos_y_filtra_por_componente[postgresql] SKIPPED (TEST_POSTGRES_URL no definida: se omite PostgreSQL)                 [ 40%]
tests/contract/test_repository_contract.py::test_candidatos_de_duplicado_sin_similitud[sqlite] PASSED                                                                                [ 41%]
tests/contract/test_repository_contract.py::test_candidatos_de_duplicado_sin_similitud[postgresql] SKIPPED (TEST_POSTGRES_URL no definida: se omite PostgreSQL)                      [ 41%]
tests/contract/test_repository_contract.py::test_el_texto_temporal_usa_microsegundos[sqlite] PASSED                                                                                  [ 41%]
tests/contract/test_repository_contract.py::test_el_texto_temporal_usa_microsegundos[postgresql] SKIPPED (TEST_POSTGRES_URL no definida: se omite PostgreSQL)                        [ 42%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[sqlite-id-vacio] PASSED                                                                          [ 42%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[sqlite-componente-vacio] PASSED                                                                  [ 42%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[sqlite-severidad-sin-politica] PASSED                                                            [ 43%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[sqlite-terminal-sin-resolucion] PASSED                                                           [ 43%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[sqlite-estado-desconocido] PASSED                                                                [ 43%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[sqlite-equipo-fuera-del-catalogo] PASSED                                                         [ 44%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[postgresql-id-vacio] SKIPPED (TEST_POSTGRES_URL no definida: se omite PostgreSQL)                [ 44%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[postgresql-componente-vacio] SKIPPED (TEST_POSTGRES_URL no definida: se omite PostgreSQL)        [ 44%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[postgresql-severidad-sin-politica] SKIPPED (TEST_POSTGRES_URL no definida: se omite PostgreSQL)  [ 45%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[postgresql-terminal-sin-resolucion] SKIPPED (TEST_POSTGRES_URL no definida: se omite PostgreSQL) [ 45%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[postgresql-estado-desconocido] SKIPPED (TEST_POSTGRES_URL no definida: se omite PostgreSQL)      [ 45%]
tests/contract/test_repository_contract.py::test_errores_de_validacion_equivalentes[postgresql-equipo-fuera-del-catalogo] SKIPPED (TEST_POSTGRES_URL no definida: se omite Postg...) [ 46%]
tests/contract/test_repository_contract.py::test_el_adaptador_no_ordena_ni_calcula_sla PASSED                                                                                        [ 46%]
tests/domain/test_duplicate_rules.py::test_umbral_exacto_de_similitud_es_equivalente PASSED                                                                                          [ 46%]
tests/domain/test_duplicate_rules.py::test_similitud_de_0_74_no_es_equivalente PASSED                                                                                                [ 47%]
tests/domain/test_duplicate_rules.py::test_frontera_exacta_de_la_ventana_es_candidata PASSED                                                                                         [ 47%]
tests/domain/test_duplicate_rules.py::test_la_ventana_la_fija_el_mas_antiguo_del_par[P0-1-True] PASSED                                                                               [ 47%]
tests/domain/test_duplicate_rules.py::test_la_ventana_la_fija_el_mas_antiguo_del_par[P0-2-False] PASSED                                                                              [ 48%]
tests/domain/test_duplicate_rules.py::test_la_ventana_la_fija_el_mas_antiguo_del_par[P1-2-True] PASSED                                                                               [ 48%]
tests/domain/test_duplicate_rules.py::test_la_ventana_la_fija_el_mas_antiguo_del_par[P1-3-False] PASSED                                                                              [ 48%]
tests/domain/test_duplicate_rules.py::test_la_ventana_la_fija_el_mas_antiguo_del_par[P2-3-True] PASSED                                                                               [ 49%]
tests/domain/test_duplicate_rules.py::test_la_ventana_la_fija_el_mas_antiguo_del_par[P2-4-False] PASSED                                                                              [ 49%]
tests/domain/test_duplicate_rules.py::test_la_ventana_la_fija_el_mas_antiguo_del_par[P3-4-True] PASSED                                                                               [ 49%]
tests/domain/test_duplicate_rules.py::test_la_ventana_la_fija_el_mas_antiguo_del_par[P3-5-False] PASSED                                                                              [ 50%]
tests/domain/test_duplicate_rules.py::test_un_candidato_terminal_nunca_es_equivalente[RESOLVED] PASSED                                                                               [ 50%]
tests/domain/test_duplicate_rules.py::test_un_candidato_terminal_nunca_es_equivalente[CLOSED] PASSED                                                                                 [ 50%]
tests/domain/test_duplicate_rules.py::test_otro_componente_no_es_equivalente PASSED                                                                                                  [ 51%]
tests/domain/test_duplicate_rules.py::test_un_candidato_sin_texto_no_es_equivalente[None] PASSED                                                                                     [ 51%]
tests/domain/test_duplicate_rules.py::test_un_candidato_sin_texto_no_es_equivalente[] PASSED                                                                                         [ 51%]
tests/domain/test_duplicate_rules.py::test_un_candidato_sin_texto_no_es_equivalente[   ] PASSED                                                                                      [ 52%]
tests/domain/test_duplicate_rules.py::test_el_mismo_identificador_no_es_equivalente PASSED                                                                                           [ 52%]
tests/domain/test_duplicate_rules.py::test_assess_sin_previos_devuelve_aviso_vacio PASSED                                                                                            [ 52%]
tests/domain/test_duplicate_rules.py::test_assess_ignora_equivalentes_posteriores PASSED                                                                                             [ 53%]
tests/domain/test_duplicate_rules.py::test_assess_informa_el_previo_ordenado_y_con_su_clave PASSED                                                                                   [ 53%]
tests/domain/test_duplicate_rules.py::test_assess_hereda_la_clave_del_original PASSED                                                                                                [ 53%]
tests/domain/test_duplicate_rules.py::test_el_mas_antiguo_no_hereda_clave_y_no_reescribe_previos PASSED                                                                              [ 54%]
tests/domain/test_duplicate_rules.py::test_assess_descarta_terminales_de_otro_componente_y_sin_texto PASSED                                                                          [ 54%]
tests/domain/test_duplicate_rules.py::test_la_tabla_de_ventanas_es_inmutable PASSED                                                                                                  [ 54%]
tests/domain/test_sla_calculator.py::test_fronteras_de_incumplimiento_y_escalamiento[P0-44-False-False] PASSED                                                                       [ 55%]
tests/domain/test_sla_calculator.py::test_fronteras_de_incumplimiento_y_escalamiento[P0-45-False-True] PASSED                                                                        [ 55%]
tests/domain/test_sla_calculator.py::test_fronteras_de_incumplimiento_y_escalamiento[P0-46-False-True] PASSED                                                                        [ 55%]
tests/domain/test_sla_calculator.py::test_fronteras_de_incumplimiento_y_escalamiento[P0-60-False-True] PASSED                                                                        [ 56%]
tests/domain/test_sla_calculator.py::test_fronteras_de_incumplimiento_y_escalamiento[P0-61-True-False] PASSED                                                                        [ 56%]
tests/domain/test_sla_calculator.py::test_fronteras_de_incumplimiento_y_escalamiento[P2-359-False-False] PASSED                                                                      [ 56%]
tests/domain/test_sla_calculator.py::test_fronteras_de_incumplimiento_y_escalamiento[P2-360-False-True] PASSED                                                                       [ 57%]
tests/domain/test_sla_calculator.py::test_fronteras_de_incumplimiento_y_escalamiento[P2-361-False-True] PASSED                                                                       [ 57%]
tests/domain/test_sla_calculator.py::test_fronteras_de_incumplimiento_y_escalamiento[P2-479-False-True] PASSED                                                                       [ 57%]
tests/domain/test_sla_calculator.py::test_fronteras_de_incumplimiento_y_escalamiento[P2-480-False-True] PASSED                                                                       [ 58%]
tests/domain/test_sla_calculator.py::test_fronteras_de_incumplimiento_y_escalamiento[P2-481-True-False] PASSED                                                                       [ 58%]
tests/domain/test_sla_calculator.py::test_p2_creado_el_viernes_no_acumula_el_fin_de_semana PASSED                                                                                    [ 58%]
tests/domain/test_sla_calculator.py::test_escalamiento_exacto_al_setenta_y_cinco_por_ciento PASSED                                                                                   [ 59%]
tests/domain/test_sla_calculator.py::test_incumplimiento_desactiva_el_escalamiento PASSED                                                                                            [ 59%]
tests/domain/test_sla_calculator.py::test_terminal_evaluado_usa_resolved_at_y_no_escala PASSED                                                                                       [ 59%]
tests/domain/test_sla_calculator.py::test_cerrado_no_escala_aunque_alcanzara_el_umbral PASSED                                                                                        [ 60%]
tests/domain/test_sla_calculator.py::test_resumen_excluye_terminales_aunque_su_sla_este_vencido PASSED                                                                               [ 60%]
tests/domain/test_sla_calculator.py::test_incidente_creado_despues_del_instante_aborta_el_resumen PASSED                                                                             [ 60%]
tests/domain/test_sla_calculator.py::test_resumen_ordena_por_severidad_minutos_e_identificador PASSED                                                                                [ 61%]
tests/domain/test_sla_calculator.py::test_totales_del_resumen_coinciden_con_el_detalle PASSED                                                                                        [ 61%]
tests/domain/test_sla_calculator.py::test_tabla_de_politicas_es_inmutable PASSED                                                                                                     [ 61%]
tests/domain/test_sla_calculator.py::test_severidad_fuera_de_la_politica_es_rechazada PASSED                                                                                         [ 62%]
tests/domain/test_sla_calculator.py::test_validar_instante_naive_acepta_naive_y_rechaza_aware PASSED                                                                                 [ 62%]
tests/domain/test_sla_calculator.py::test_evaluate_sla_detail_rechaza_aware_en_los_tres_campos[incidente0-created_at] PASSED                                                         [ 62%]
tests/domain/test_sla_calculator.py::test_evaluate_sla_detail_rechaza_aware_en_los_tres_campos[incidente1-resolved_at] PASSED                                                        [ 63%]
tests/domain/test_sla_calculator.py::test_resolver_ventana_temporal_deriva_la_ventana_de_la_politica PASSED                                                                          [ 63%]
tests/domain/test_sla_calculator.py::test_resolver_ventana_congela_el_fin_en_resolved_at PASSED                                                                                      [ 63%]
tests/domain/test_sla_calculator.py::test_referencia_anterior_a_la_creacion_se_rechaza_tambien_en_terminales PASSED                                                                  [ 64%]
tests/domain/test_sla_calculator.py::test_terminal_sin_resolved_at_es_dato_incoherente PASSED                                                                                        [ 64%]
tests/domain/test_sla_calculator.py::test_resolved_at_anterior_a_created_at_es_dato_incoherente PASSED                                                                               [ 64%]
tests/domain/test_sla_calculator.py::test_severidad_desconocida_es_dato_incoherente_en_la_auditoria PASSED                                                                           [ 65%]
tests/domain/test_sla_calculator.py::test_evaluate_sla_detail_conserva_los_valores_de_h002 PASSED                                                                                    [ 65%]
tests/domain/test_sla_calculator.py::test_evaluate_sla_detail_p2_viernes_a_lunes PASSED                                                                                              [ 65%]
tests/domain/test_sla_calculator.py::test_terminal_congelado_antes_y_despues_de_la_resolucion[referencia0] PASSED                                                                    [ 66%]
tests/domain/test_sla_calculator.py::test_terminal_congelado_antes_y_despues_de_la_resolucion[referencia1] PASSED                                                                    [ 66%]
tests/domain/test_sla_calculator.py::test_referencia_igual_a_la_creacion_da_cero PASSED                                                                                              [ 66%]
tests/domain/test_triage_rules.py::test_clasificacion_de_los_reportes_de_muestra[INC-1001-texto0-P0-payments-gateway-Backend-Core] PASSED                                            [ 66%]
tests/domain/test_triage_rules.py::test_clasificacion_de_los_reportes_de_muestra[INC-1002-texto1-P2-auth-identity-Security-IAM] PASSED                                               [ 67%]
tests/domain/test_triage_rules.py::test_clasificacion_de_los_reportes_de_muestra[INC-1003-texto2-P2-reporting-api-otros] PASSED                                                      [ 67%]
tests/domain/test_triage_rules.py::test_clasificacion_de_los_reportes_de_muestra[INC-1004-texto3-P3-reporting-api-otros] PASSED                                                      [ 67%]
tests/domain/test_triage_rules.py::test_clasificacion_de_los_reportes_de_muestra[INC-1005-texto4-P1-database-cluster-Data-DBA] PASSED                                                [ 68%]
tests/domain/test_triage_rules.py::test_clasificacion_de_los_reportes_de_muestra[INC-1006-texto5-P0-payments-gateway-Backend-Core] PASSED                                            [ 68%]
tests/domain/test_triage_rules.py::test_clasificacion_de_los_reportes_de_muestra[INC-1007-texto6-P0-security-audit-Security-IAM] PASSED                                              [ 68%]
tests/domain/test_triage_rules.py::test_clasificacion_de_los_reportes_de_muestra[INC-1008-texto7-P2-reporting-api-otros] PASSED                                                      [ 69%]
tests/domain/test_triage_rules.py::test_clasificacion_de_los_reportes_de_muestra[INC-1009-texto8-P2-reporting-api-otros] PASSED                                                      [ 69%]
tests/domain/test_triage_rules.py::test_clasificacion_de_los_reportes_de_muestra[INC-1010-texto9-P3-infra-certificates-Platform-SRE] PASSED                                          [ 69%]
tests/domain/test_triage_rules.py::test_palabras_emocionales_no_escalan_a_p0 PASSED                                                                                                  [ 70%]
tests/domain/test_triage_rules.py::test_reporte_sin_palabras_clave_usa_el_valor_por_defecto PASSED                                                                                   [ 70%]
tests/domain/test_triage_rules.py::test_pagos_gana_sobre_gateway_en_el_enrutamiento PASSED                                                                                           [ 70%]
tests/domain/test_triage_rules.py::test_la_clasificacion_es_determinista PASSED                                                                                                      [ 71%]
tests/domain/test_triage_rules.py::test_el_resultado_no_es_mutable PASSED                                                                                                            [ 71%]
tests/test_spec_001_triage.py::test_e01_caida_critica_http_502_en_la_pasarela_de_pagos PASSED                                                                                        [ 71%]
tests/test_spec_001_triage.py::test_e02_cuenta_bloqueada_que_menciona_hoy_no_es_p0 PASSED                                                                                            [ 72%]
tests/test_spec_001_triage.py::test_e03_entradas_vacias_o_con_solo_espacios_devuelven_422 PASSED                                                                                     [ 72%]
tests/test_spec_001_triage.py::test_e04_paridad_de_la_cli_con_el_caso_critico PASSED                                                                                                 [ 72%]
tests/test_spec_001_triage.py::test_paridad_http_y_cli_sobre_los_reportes_de_muestra PASSED                                                                                          [ 73%]
tests/test_spec_002_summary.py::test_us1_resumen_global_excluye_terminales PASSED                                                                                                    [ 73%]
tests/test_spec_002_summary.py::test_us1_total_incumplido_coincide_con_el_detalle PASSED                                                                                             [ 73%]
tests/test_spec_002_summary.py::test_us1_detalle_completo_por_incidente PASSED                                                                                                       [ 74%]
tests/test_spec_002_summary.py::test_us1_resumen_vacio_termina_con_exito PASSED                                                                                                      [ 74%]
tests/test_spec_002_summary.py::test_us1_titulo_con_acentos_y_comillas_no_se_altera PASSED                                                                                           [ 74%]
tests/test_spec_002_summary.py::test_us1_sin_reference_time_sobre_base_vacia PASSED                                                                                                  [ 75%]
tests/test_spec_002_summary.py::test_us1_reference_time_invalido_devuelve_422[2026-11-20T12:00:00+00:00] PASSED                                                                      [ 75%]
tests/test_spec_002_summary.py::test_us1_reference_time_invalido_devuelve_422[2026-11-20 12:00:00] PASSED                                                                            [ 75%]
tests/test_spec_002_summary.py::test_us1_reference_time_invalido_devuelve_422[2026-13-40T12:00:00] PASSED                                                                            [ 76%]
tests/test_spec_002_summary.py::test_us1_parametro_desconocido_devuelve_422[parametro0] PASSED                                                                                       [ 76%]
tests/test_spec_002_summary.py::test_us1_parametro_desconocido_devuelve_422[parametro1] PASSED                                                                                       [ 76%]
tests/test_spec_002_summary.py::test_us1_incoherencia_temporal_devuelve_409_sin_totales PASSED                                                                                       [ 77%]
tests/test_spec_002_summary.py::test_us1_terminal_con_sla_vencido_no_aparece PASSED                                                                                                  [ 77%]
tests/test_spec_002_summary.py::test_us2_paridad_http_y_cli PASSED                                                                                                                   [ 77%]
tests/test_spec_002_summary.py::test_us2_paridad_en_resultado_vacio PASSED                                                                                                           [ 78%]
tests/test_spec_002_summary.py::test_us2_titulo_especial_identico_en_ambos_canales PASSED                                                                                            [ 78%]
tests/test_spec_002_summary.py::test_us2_fronteras_de_sla_coinciden_en_los_tres_caminos PASSED                                                                                       [ 78%]
tests/test_spec_002_summary.py::test_us2_fecha_invalida_sale_con_codigo_2[2026-11-20T12:00:00+00:00] PASSED                                                                          [ 79%]
tests/test_spec_002_summary.py::test_us2_fecha_invalida_sale_con_codigo_2[2026-11-20 12:00:00] PASSED                                                                                [ 79%]
tests/test_spec_002_summary.py::test_us2_fecha_invalida_sale_con_codigo_2[no-es-fecha] PASSED                                                                                        [ 79%]
tests/test_spec_002_summary.py::test_us2_incoherencia_temporal_sale_con_codigo_1 PASSED                                                                                              [ 80%]
tests/test_spec_002_summary.py::test_us3_filtro_por_componente_en_ambos_canales PASSED                                                                                               [ 80%]
tests/test_spec_002_summary.py::test_us3_componente_sin_coincidencias_es_exito PASSED                                                                                                [ 80%]
tests/test_spec_002_summary.py::test_us3_espacios_sobrantes_se_ignoran PASSED                                                                                                        [ 81%]
tests/test_spec_002_summary.py::test_us3_filtro_ausente_o_vacio_equivale_a_todos[parametros0] PASSED                                                                                 [ 81%]
tests/test_spec_002_summary.py::test_us3_filtro_ausente_o_vacio_equivale_a_todos[parametros1] PASSED                                                                                 [ 81%]
tests/test_spec_002_summary.py::test_us3_filtro_ausente_o_vacio_equivale_a_todos[parametros2] PASSED                                                                                 [ 82%]
tests/test_spec_002_summary.py::test_us3_componente_demasiado_largo_http PASSED                                                                                                      [ 82%]
tests/test_spec_002_summary.py::test_us3_componente_demasiado_largo_cli PASSED                                                                                                       [ 82%]
tests/test_spec_003_lifecycle_sla.py::test_us1_alta_http_clasifica_y_persiste_en_open PASSED                                                                                         [ 83%]
tests/test_spec_003_lifecycle_sla.py::test_us1_titulo_derivado_de_la_primera_linea_con_maximo_200 PASSED                                                                             [ 83%]
tests/test_spec_003_lifecycle_sla.py::test_us1_alta_por_cli_y_recuperacion_tras_reinicio PASSED                                                                                      [ 83%]
tests/test_spec_003_lifecycle_sla.py::test_us1_el_registrado_aparece_una_sola_vez_en_el_resumen PASSED                                                                               [ 84%]
tests/test_spec_003_lifecycle_sla.py::test_us1_conflicto_de_identificador_es_conflicto_sin_sobrescribir PASSED                                                                       [ 84%]
tests/test_spec_003_lifecycle_sla.py::test_us1_entradas_invalidas_son_422_y_salida_2[payload0-CREATE_ID_VACIO] PASSED                                                                [ 84%]
tests/test_spec_003_lifecycle_sla.py::test_us1_entradas_invalidas_son_422_y_salida_2[payload1-CREATE_ID_VACIO] PASSED                                                                [ 85%]
tests/test_spec_003_lifecycle_sla.py::test_us1_entradas_invalidas_son_422_y_salida_2[payload2-CREATE_ID_DEMASIADO_LARGO] PASSED                                                      [ 85%]
tests/test_spec_003_lifecycle_sla.py::test_us1_entradas_invalidas_son_422_y_salida_2[payload3-CREATE_TEXTO_VACIO] PASSED                                                             [ 85%]
tests/test_spec_003_lifecycle_sla.py::test_us1_entradas_invalidas_son_422_y_salida_2[payload4-CREATE_TEXTO_DEMASIADO_LARGO] PASSED                                                   [ 86%]
tests/test_spec_003_lifecycle_sla.py::test_us1_created_at_invalido_es_422_y_salida_2[2026-11-20 10:00:00] PASSED                                                                     [ 86%]
tests/test_spec_003_lifecycle_sla.py::test_us1_created_at_invalido_es_422_y_salida_2[2026-11-20T10:00:00+00:00] PASSED                                                               [ 86%]
tests/test_spec_003_lifecycle_sla.py::test_us1_created_at_invalido_es_422_y_salida_2[no-es-fecha] PASSED                                                                             [ 87%]
tests/test_spec_003_lifecycle_sla.py::test_us2_aviso_simple_en_la_misma_respuesta PASSED                                                                                             [ 87%]
tests/test_spec_003_lifecycle_sla.py::test_us2_sin_falsos_positivos[terminal] PASSED                                                                                                 [ 87%]
tests/test_spec_003_lifecycle_sla.py::test_us2_sin_falsos_positivos[otro_componente] PASSED                                                                                          [ 88%]
tests/test_spec_003_lifecycle_sla.py::test_us2_sin_falsos_positivos[similitud] PASSED                                                                                                [ 88%]
tests/test_spec_003_lifecycle_sla.py::test_us2_sin_falsos_positivos[ventana] PASSED                                                                                                  [ 88%]
tests/test_spec_003_lifecycle_sla.py::test_us2_sin_falsos_positivos[sin_texto] PASSED                                                                                                [ 89%]
tests/test_spec_003_lifecycle_sla.py::test_us2_hereda_la_clave_del_original PASSED                                                                                                   [ 89%]
tests/test_spec_003_lifecycle_sla.py::test_us2_el_nuevo_mas_antiguo_actua_como_original PASSED                                                                                       [ 89%]
tests/test_spec_003_lifecycle_sla.py::test_us2_duplicate_of_ordenado_y_sin_fusionar PASSED                                                                                           [ 90%]
tests/test_spec_003_lifecycle_sla.py::test_us2_concurrencia_serializada_por_componente PASSED                                                                                        [ 90%]
tests/test_spec_003_lifecycle_sla.py::test_us3_sla_activo_con_contexto_completo PASSED                                                                                               [ 90%]
tests/test_spec_003_lifecycle_sla.py::test_us3_fronteras_p0_60_y_61[60-False-0-True] PASSED                                                                                          [ 91%]
tests/test_spec_003_lifecycle_sla.py::test_us3_fronteras_p0_60_y_61[61-True--1-False] PASSED                                                                                         [ 91%]
tests/test_spec_003_lifecycle_sla.py::test_us3_p1_con_180_minutos_requiere_escalamiento PASSED                                                                                       [ 91%]
tests/test_spec_003_lifecycle_sla.py::test_us3_p2_de_viernes_a_lunes_excluye_el_fin_de_semana PASSED                                                                                 [ 92%]
tests/test_spec_003_lifecycle_sla.py::test_us3_terminal_congelado_antes_y_despues_de_la_resolucion[2026-11-20T10:10:00] PASSED                                                       [ 92%]
tests/test_spec_003_lifecycle_sla.py::test_us3_terminal_congelado_antes_y_despues_de_la_resolucion[2026-11-25T10:10:00] PASSED                                                       [ 92%]
tests/test_spec_003_lifecycle_sla.py::test_us3_referencia_anterior_a_la_creacion_es_422_y_salida_1 PASSED                                                                            [ 93%]
tests/test_spec_003_lifecycle_sla.py::test_us3_incidente_inexistente_es_404_y_salida_1 PASSED                                                                                        [ 93%]
tests/test_spec_003_lifecycle_sla.py::test_us3_referencia_omitida_informa_el_instante_aplicado PASSED                                                                                [ 93%]
tests/test_spec_003_lifecycle_sla.py::test_us3_referencia_con_zona_es_422_y_salida_2 PASSED                                                                                          [ 94%]
tests/test_spec_003_lifecycle_sla.py::test_us3_identificador_solo_espacios_es_entrada_invalida PASSED                                                                                [ 94%]
tests/test_spec_003_lifecycle_sla.py::test_us4_paridad_estricta_del_alta PASSED                                                                                                      [ 94%]
tests/test_spec_003_lifecycle_sla.py::test_us4_paridad_estricta_del_sla PASSED                                                                                                       [ 95%]
tests/test_spec_003_lifecycle_sla.py::test_us4_fallos_equivalentes_comparten_codigo PASSED                                                                                           [ 95%]
tests/test_spec_004_runtime_health.py::test_bdd_e01_el_servicio_confirma_que_su_base_responde PASSED                                                                                 [ 95%]
tests/test_spec_004_runtime_health.py::test_bdd_e02_la_consola_confirma_la_misma_conectividad PASSED                                                                                 [ 96%]
tests/test_spec_004_runtime_health.py::test_bdd_e03_una_base_inaccesible_se_informa_como_no_disponible PASSED                                                                        [ 96%]
tests/test_spec_004_runtime_health.py::test_bdd_e04_la_consola_informa_la_indisponibilidad PASSED                                                                                    [ 96%]
tests/test_spec_004_runtime_health.py::test_la_configuracion_invalida_sale_2_sin_documento PASSED                                                                                    [ 97%]
tests/test_spec_004_runtime_health.py::test_el_fallo_interno_del_comando_sale_1_sin_traza PASSED                                                                                     [ 97%]
tests/test_spec_004_runtime_health.py::test_bdd_e05_ambos_canales_coinciden_al_informar_la_salud[True] PASSED                                                                        [ 97%]
tests/test_spec_004_runtime_health.py::test_bdd_e05_ambos_canales_coinciden_al_informar_la_salud[False] PASSED                                                                       [ 98%]
tests/test_spec_004_runtime_health.py::test_bdd_e06_el_desarrollo_local_sigue_funcionando_sin_base_dedicada PASSED                                                                   [ 98%]
tests/test_spec_004_runtime_health.py::test_el_motor_caido_no_cambia_el_error_generico_de_negocio PASSED                                                                             [ 98%]
tests/test_spec_004_runtime_health.py::test_el_dockerfile_es_multietapa_reproducible_y_sin_privilegios PASSED                                                                        [ 99%]
tests/test_spec_004_runtime_health.py::test_el_dockerignore_excluye_secretos_y_artefactos PASSED                                                                                     [ 99%]
tests/test_spec_004_runtime_health.py::test_el_compose_define_db_y_api_con_arranque_ordenado PASSED                                                                                  [ 99%]
tests/test_spec_004_runtime_health.py::test_el_env_example_documenta_marcadores_no_secretos PASSED                                                                                   [100%]

==================================================================================== warnings summary =====================================================================================
.venv\lib\site-packages\fastapi\testclient.py:1
  D:\Educación\Otros Estudios\Ingeniería de sotfware\starter-project\.venv\lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================================================================= 292 passed, 11 skipped, 1 warning in 16.68s =======================================================================
```

- **Evidencia de CLI Typer y containerización (`docker compose config` / `docker compose up --build`)**:

```text
**docker compose config**
name: incidentops
services:
  api:
    deploy:
      replicas: 1
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://incidentops:incidentops_local@db:5432/incidentops
    networks:
      default: null
    build:
      context: D:\Educación\Otros Estudios\Ingeniería de sotfware\starter-project
      dockerfile: Dockerfile
    depends_on:
      db:
        condition: service_healthy
        required: true
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',
          timeout=3)
      timeout: 5s
      interval: 10s
      retries: 6
      start_period: 10s
    ports:
      - mode: ingress
        target: 8000
        published: "8000"
        protocol: tcp
  db:
    restart: unless-stopped
    environment:
      POSTGRES_DB: incidentops
      POSTGRES_PASSWORD: incidentops_local
      POSTGRES_USER: incidentops
    image: postgres:16-alpine
    networks:
      default: null
    volumes:
      - type: volume
        source: incidentops_pgdata
        target: /var/lib/postgresql/data
        volume: {}
    healthcheck:
      test:
        - CMD-SHELL
        - pg_isready -U incidentops -d incidentops
      timeout: 3s
      interval: 5s
      retries: 12
networks:
  default:
    name: incidentops_default
volumes:
  incidentops_pgdata:
    name: incidentops_pgdata

**docker compose up --build**:

[+] Building 3.5s (20/20) FINISHED                                                                                                                                                          
 => [internal] load local bake definitions                                                                                                                                             0.1s
 => => reading from stdin 593B                                                                                                                                                         0.0s
 => [internal] load build definition from Dockerfile                                                                                                                                   0.0s
 => => transferring dockerfile: 1.06kB                                                                                                                                                 0.0s
 => resolve image config for docker-image://docker.io/docker/dockerfile:1                                                                                                              1.0s
 => CACHED docker-image://docker.io/docker/dockerfile:1@sha256:572cebbc2b15e6f84c077742952674889cb63cd5e9b80abdffcbe587b6f19183                                                        0.0s
 => => resolve docker.io/docker/dockerfile:1@sha256:572cebbc2b15e6f84c077742952674889cb63cd5e9b80abdffcbe587b6f19183                                                                   0.0s
 => [internal] load metadata for ghcr.io/astral-sh/uv:0.13.8                                                                                                                           0.9s
 => [internal] load metadata for docker.io/library/python:3.12-slim                                                                                                                    0.7s
 => [internal] load .dockerignore                                                                                                                                                      0.0s
 => => transferring context: 420B                                                                                                                                                      0.0s
 => FROM ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85                                                                           0.0s
 => => resolve ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85                                                                     0.0s
 => [builder 1/5] FROM docker.io/library/python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b                                                      0.1s
 => => resolve docker.io/library/python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b                                                              0.1s
 => [internal] load build context                                                                                                                                                      0.0s
 => => transferring context: 5.71kB                                                                                                                                                    0.0s
 => CACHED [runtime 2/5] WORKDIR /app                                                                                                                                                  0.0s
 => CACHED [builder 2/5] COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/                                                                                                        0.0s
 => CACHED [builder 3/5] WORKDIR /app                                                                                                                                                  0.0s
 => CACHED [builder 4/5] COPY pyproject.toml uv.lock README.md ./                                                                                                                      0.0s
 => CACHED [builder 5/5] RUN uv sync --frozen --no-dev --no-install-project                                                                                                            0.0s
 => CACHED [runtime 3/5] COPY --from=builder /app/.venv /app/.venv                                                                                                                     0.0s
 => CACHED [runtime 4/5] COPY src ./src                                                                                                                                                0.0s
 => CACHED [runtime 5/5] RUN groupadd --system --gid 10001 incidentops     && useradd --system --uid 10001 --gid incidentops --no-create-home incidentops                              0.0s
 => exporting to image                                                                                                                                                                 0.1s
 => => exporting layers                                                                                                                                                                0.0s
 => => exporting manifest sha256:acf38e591d80349a69858ab234c29f1ca4cc2a32eaea7f5976833d86bab23195                                                                                      0.0s
 => => exporting config sha256:005254729a4d9002ae743869b92665d58df2058076c200d025c2de7e9ab0118f                                                                                        0.0s
 => => exporting attestation manifest sha256:9ed228263b06b8532d186667040ac0fb89a763730e3ae3b11c45af93ff15b969                                                                          0.0s
 => => exporting manifest list sha256:9d0184f6fc5e3982dd45bdbecb4fc41e66cff0efb8efc94bd1ef373c0b46e9ae                                                                                 0.0s
 => => naming to docker.io/library/incidentops-api:latest                                                                                                                              0.0s
 => => unpacking to docker.io/library/incidentops-api:latest                                                                                                                           0.0s
 => resolving provenance for metadata file                                                                                                                                             0.0s
[+] up 4/4
 ✔ Image incidentops-api       Built                                                                                                                                                   10.2s
 ✔ Network incidentops_default Created                                                                                                                                                  0.0s
 ✔ Container incidentops-db-1  Created                                                                                                                                                  0.1s
 ✔ Container incidentops-api-1 Created                                                                                                                                                  0.1s
Attaching to api-1, db-1
Container incidentops-db-1 Waiting 
db-1  | 
db-1  | PostgreSQL Database directory appears to contain a database; Skipping initialization
db-1  | 
db-1  | 2026-11-23 16:26:35.341 UTC [1] LOG:  starting PostgreSQL 16.16 on x86_64-pc-linux-musl, compiled by gcc (Alpine 15.2.0) 15.2.0, 64-bit
db-1  | 2026-11-23 16:26:35.341 UTC [1] LOG:  listening on IPv4 address "0.0.0.0", port 5432
db-1  | 2026-11-23 16:26:35.341 UTC [1] LOG:  listening on IPv6 address "::", port 5432
db-1  | 2026-11-23 16:26:35.349 UTC [1] LOG:  listening on Unix socket "/run/postgresql/.s.PGSQL.5432"
db-1  | 2026-11-23 16:26:35.358 UTC [29] LOG:  database system was shut down at 2026-11-23 16:15:22 UTC
db-1  | 2026-11-23 16:26:35.368 UTC [1] LOG:  database system is ready to accept connections
Container incidentops-db-1 Healthy 
api-1  | INFO:     Started server process [1]
api-1  | INFO:     Waiting for application startup.
api-1  | INFO:     Application startup complete.
api-1  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
api-1  | INFO:     127.0.0.1:51922 - "GET /health HTTP/1.1" 200 OK

```
