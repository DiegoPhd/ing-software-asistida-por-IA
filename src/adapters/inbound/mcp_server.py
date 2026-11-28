"""Adaptador de entrada MCP (stdio) sobre los casos de uso de IncidentOps.

Tercer adaptador primario, junto a REST y CLI: traduce las llamadas de un
cliente LLM a `IncidentService` y devuelve los mismos documentos de transporte
que los otros canales. No clasifica, no calcula SLA, no detecta duplicados ni
importa la persistencia concreta: solo compone el caso de uso a través de
`src.adapters.outbound.factory` y serializa con los contratos compartidos de
`src.adapters.inbound/`.

`stdout` pertenece en exclusiva al protocolo JSON-RPC del transporte stdio; todo
diagnóstico se escribe en `stderr` mediante `_log`. Un solo `print` sin `file=`
corrompería la sesión con el cliente.

Uso:
    uv run python -m src.adapters.inbound.mcp_server
"""

import json
import sys
import threading
from dataclasses import asdict
from typing import Any, Callable, Dict, Optional

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from src.adapters.inbound.health_contract import to_health_response
from src.adapters.inbound.lifecycle_contract import (
    to_incident_created_response,
    to_sla_evaluation_response,
)
from src.adapters.inbound.problem import build_problem
from src.adapters.inbound.summary_contract import to_summary_response
from src.adapters.inbound.temporal_contract import parse_instante_naive
from src.adapters.outbound.factory import ConfigurationError, build_incident_service
from src.application.services import (
    CREATE_CREACION_INVALIDA,
    CREATE_ERROR_INTERNO,
    SLA_ERROR_INTERNO,
    SLA_REFERENCIA_INVALIDA,
    SUMMARY_ERROR_INTERNO,
    SUMMARY_REFERENCIA_INVALIDA,
    DataInconsistencyError,
    IncidentAlreadyExistsError,
    IncidentNotFoundError,
    IncidentService,
    ValidationError,
)

NOMBRE_SERVIDOR = "incidentops"
TITULO_SERVIDOR = "IncidentOps · Operación de incidentes"
VERSION_SERVIDOR = "0.5.0"

# Código propio del adaptador para un fallo no previsto del triaje; el resto de
# rutas ya publica su `*_ERROR_INTERNO` desde el caso de uso.
TRIAGE_ERROR_INTERNO = "TRIAGE_ERROR_INTERNO"
HEALTH_ERROR_INTERNO = "HEALTH_ERROR_INTERNO"

# Mismo código que la CLI: la fábrica no pudo interpretar `DATABASE_URL`.
CONFIG_DATABASE_URL_INVALIDA = "CONFIG_DATABASE_URL_INVALIDA"

INSTRUCCIONES = """Servidor MCP de IncidentOps para operar incidentes.

Flujo recomendado:
1. `triage_incident` previsualiza la severidad, el componente y el equipo
   recomendado de un reporte, sin escribir nada.
2. `create_incident` es la única herramienta que persiste: da de alta el
   incidente en estado OPEN, detecta duplicados activos del mismo componente y
   nunca modifica incidentes anteriores.
3. `get_active_incidents_summary` resume los incidentes en OPEN o IN_PROGRESS
   con su consumo de SLA.
4. `evaluate_incident_sla` audita un incidente concreto ya almacenado.
5. `check_health` comprueba la conectividad con la base de datos.

Las fechas son ISO 8601 naive con separador `T` y sin zona horaria
(`YYYY-MM-DDTHH:MM:SS[.ffffff]`). Cuando un instante opcional se omite, el
servicio usa el reloj del sistema. Los errores se devuelven como documento
problem+json con un `code` estable y un `status` equivalente al HTTP del canal
REST."""


def _log(mensaje: str) -> None:
    """Escribe un diagnóstico en `stderr`, nunca en `stdout`.

    `stdout` transporta el JSON-RPC de stdio: cualquier texto ajeno al protocolo
    rompe la sesión con el cliente. Por eso el único punto de escritura
    diagnóstica del adaptador es esta función, que ni siquiera usa `print` para
    que la pureza del canal sea verificable de forma estática.

    Args:
        mensaje: Texto ya formateado; no debe contener credenciales ni el DSN.
    """
    sys.stderr.write(f"[mcp] {mensaje}\n")
    sys.stderr.flush()


def _documento(code: str, field: str, detail: str, status: int) -> str:
    """Serializa un error de aplicación como documento problem+json.

    Reutiliza `build_problem` para conservar los mismos `code`, `status`,
    `detail` y `errors[].field` que publican REST y CLI, de modo que un cliente
    pueda tratar los tres canales igual.

    Args:
        code: Código estable del contrato (`CREATE_ID_CONFLICTO`, `SLA_ID_VACIO`…).
        field: Campo responsable del fallo.
        detail: Explicación legible para el operador.
        status: Estado HTTP equivalente del canal REST.

    Returns:
        Texto JSON del documento de error.
    """
    return json.dumps(
        build_problem(code, field, detail, status=status), ensure_ascii=False
    )


def _ejecutar(
    operacion: Callable[[], Dict[str, Any]],
    codigo_interno: str,
    campo: str,
) -> Dict[str, Any]:
    """Ejecuta una operación del caso de uso y traduce sus fallos a `ToolError`.

    Centraliza el contrato de errores del adaptador: las excepciones de
    aplicación se convierten en `ToolError` con el documento problem+json y el
    `status` que ya usa el canal REST; los fallos inesperados se registran en
    `stderr` y se publican sin traza. Un `ToolError` ya construido se propaga
    intacto.

    Args:
        operacion: Cierre sin argumentos que invoca al servicio y devuelve el
            diccionario serializado de la herramienta.
        codigo_interno: Código `*_ERROR_INTERNO` de la ruta para un fallo no
            previsto.
        campo: Nombre de la herramienta o campo que se cita en ese fallo.

    Returns:
        El diccionario devuelto por `operacion`.

    Raises:
        ToolError: siempre que la operación falle; el mensaje contiene el
            documento problem+json serializado.
    """
    try:
        return operacion()
    except ToolError:
        raise
    except ValidationError as exc:
        raise ToolError(_documento(exc.code, exc.field, exc.detail, 422)) from exc
    except IncidentAlreadyExistsError as exc:
        raise ToolError(_documento(exc.code, exc.field, exc.detail, 409)) from exc
    except IncidentNotFoundError as exc:
        raise ToolError(_documento(exc.code, exc.field, exc.detail, 404)) from exc
    except DataInconsistencyError as exc:
        raise ToolError(
            _documento(exc.code, exc.field, exc.detail, exc.status)
        ) from exc
    except ConfigurationError as exc:
        _log(f"Configuración inválida de DATABASE_URL: {exc}")
        raise ToolError(
            _documento(
                CONFIG_DATABASE_URL_INVALIDA, "DATABASE_URL", str(exc), 422
            )
        ) from exc
    except Exception as exc:  # noqa: BLE001 - el borde traduce cualquier fallo
        _log(f"Fallo inesperado en {campo}: {type(exc).__name__}: {exc}")
        raise ToolError(
            _documento(
                codigo_interno,
                campo,
                "No fue posible completar la operación solicitada.",
                500,
            )
        ) from exc


class _ServicioPerezoso:
    """Resuelve `IncidentService` en la primera herramienta y lo reutiliza.

    La construcción es perezosa para que importar el módulo y arrancar el
    transporte stdio no dependan de `DATABASE_URL`: una configuración inválida
    se convierte en error de herramienta, no en una traza de importación. El
    cerrojo protege la inicialización porque el SDK ejecuta las funciones
    síncronas en un hilo de trabajo.
    """

    def __init__(self, servicio: Optional[IncidentService] = None) -> None:
        self._instancia = servicio
        self._cerrojo = threading.Lock()

    def obtener(self) -> IncidentService:
        """Devuelve el caso de uso inyectado o lo construye una única vez.

        Returns:
            La instancia compartida de `IncidentService`.

        Raises:
            ConfigurationError: si `DATABASE_URL` no se puede interpretar; la
                traducción a `ToolError` ocurre en `_ejecutar`.
        """
        if self._instancia is not None:
            return self._instancia
        with self._cerrojo:
            if self._instancia is None:
                _log("Construyendo IncidentService desde la fábrica de salida.")
                self._instancia = build_incident_service()
                _log("IncidentService construido y reutilizado por el servidor.")
        return self._instancia


def create_server(service: Optional[IncidentService] = None) -> MCPServer:
    """Construye el servidor MCP y registra las herramientas del caso de uso.

    Ninguna herramienta contiene reglas de negocio: cada una valida el formato
    de sus fechas con el parser compartido, delega en `IncidentService` y
    serializa con el contrato de transporte correspondiente.

    Args:
        service: caso de uso ya compuesto; `None` delega en
            `build_incident_service()` en la primera invocación. Permite probar
            el adaptador con dobles en memoria sin tocar la fábrica.

    Returns:
        Servidor `MCPServer` listo para `run()` o para `call_tool()`.
    """
    mcp = MCPServer(
        name=NOMBRE_SERVIDOR,
        title=TITULO_SERVIDOR,
        version=VERSION_SERVIDOR,
        instructions=INSTRUCCIONES,
        log_level="WARNING",
    )
    servicio = _ServicioPerezoso(service)

    @mcp.tool()
    def triage_incident(incident_id: str, raw_text: str) -> dict:
        """Clasifica un reporte de incidente y devuelve su triaje, sin persistir nada.

        Funcionamiento:
            Aplica las reglas de impacto del dominio sobre el texto recibido y
            devuelve la severidad, el componente afectado, el equipo
            recomendado y la justificación. Es una operación de solo lectura:
            no crea, modifica ni consulta incidentes almacenados y no detecta
            duplicados reales, por lo que `duplicate_group_key` siempre llega
            en `None`. Úsala para previsualizar cómo se clasificará un reporte
            antes de darlo de alta con `create_incident`.

        Args:
            incident_id: Identificador del reporte, por ejemplo `INC-1001`.
                Debe ser texto no vacío de hasta 64 caracteres; se recortan los
                espacios de los extremos. No necesita existir en la base de
                datos.
            raw_text: Texto original del reporte en lenguaje natural, de hasta
                10 000 caracteres. No puede estar vacío ni contener solo
                espacios. La clasificación depende del impacto descrito
                (indisponibilidad, timeouts, lentitud, cosmética), nunca de
                palabras como "urgente".

        Returns:
            Diccionario con las claves `incident_id`, `severity` (`P0`-`P3`),
            `component`, `recommended_team`, `rationale` y
            `duplicate_group_key` (siempre `None` en esta herramienta).

        Errores:
            Lanza un error de herramienta con documento problem+json cuando
            `incident_id` está vacío o supera 64 caracteres (`TRIAGE_ID_VACIO`,
            `TRIAGE_ID_DEMASIADO_LARGO`) o cuando `raw_text` está vacío o
            supera 10 000 caracteres (`TRIAGE_TEXTO_VACIO`,
            `TRIAGE_TEXTO_DEMASIADO_LARGO`). No toca la base de datos, así que
            no falla por conexión.
        """
        return _ejecutar(
            lambda: asdict(
                servicio.obtener().triage_incident(incident_id, raw_text)
            ),
            TRIAGE_ERROR_INTERNO,
            "triage_incident",
        )

    @mcp.tool()
    def create_incident(
        title: str,
        raw_text: str,
        incident_id: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> dict:
        """Registra un incidente nuevo en estado OPEN y avisa de duplicados activos.

        Funcionamiento:
            Es la única herramienta que persiste: clasifica el reporte, busca
            incidentes activos equivalentes del mismo componente y guarda el
            alta con un `INSERT` estricto. Nunca reemplaza, fusiona ni modifica
            incidentes anteriores; si encuentra equivalentes, solo marca
            `is_duplicate`, rellena `duplicate_group_key` con el identificador
            del original más antiguo y enumera en `duplicate_of` los
            identificadores previos. Si el identificador ya existe, la
            operación falla y no se escribe nada. Llámala solo cuando el
            operador haya confirmado el alta; para explorar usa
            `triage_incident`.

        Args:
            title: Título breve y legible del incidente. Obligatorio: no puede
                estar vacío ni contener solo espacios, y no supera el máximo de
                título del dominio. El servicio sabe derivar el título del
                texto cuando se omite, pero esta herramienta exige que lo
                envíes; usa la primera línea del reporte o un resumen de una
                frase.
            raw_text: Texto original completo del reporte, de hasta 10 000
                caracteres. No puede estar vacío ni contener solo espacios. Se
                conserva sin normalizar y es la base de la clasificación y de
                la comparación de similitud.
            incident_id: Identificador único del incidente, por ejemplo
                `INC-1001`, de hasta 64 caracteres. Si es `None` o solo
                espacios se rechaza con `CREATE_ID_VACIO`: esta herramienta no
                inventa identificadores, porque la política de numeración es
                del operador y debe coincidir con la de REST y CLI.
            created_at: Instante de creación en ISO 8601 naive con separador
                `T`, `YYYY-MM-DDTHH:MM:SS[.ffffff]` y sin zona horaria. Si es
                `None`, el servicio resuelve el instante actual una sola vez
                con su reloj inyectado.

        Returns:
            Diccionario con `incident_id`, `title`, `component`, `severity`,
            `recommended_team`, `status` (siempre `OPEN`), `created_at`,
            `resolved_at` (`None` en el alta), `duplicate_group_key`,
            `is_duplicate` y `duplicate_of` (lista de identificadores previos
            equivalentes, vacía si no hay duplicado).

        Errores:
            `CREATE_ID_VACIO` o `CREATE_ID_DEMASIADO_LARGO` por el
            identificador; `CREATE_TEXTO_VACIO` o `CREATE_TEXTO_DEMASIADO_LARGO`
            por el texto; `CREATE_TITULO_VACIO` o `CREATE_TITULO_DEMASIADO_LARGO`
            por el título; `CREATE_CREACION_INVALIDA` si `created_at` no
            respeta el formato naive; `CREATE_ID_CONFLICTO` (409) si el
            identificador ya existe; `CONFIG_DATABASE_URL_INVALIDA` (422) si la
            configuración de la base es inválida y `CREATE_ERROR_INTERNO`
            (500) ante cualquier otro fallo, incluida una base inaccesible.
        """

        def operacion() -> Dict[str, Any]:
            instante = parse_instante_naive(
                created_at, "created_at", CREATE_CREACION_INVALIDA
            )
            resultado = servicio.obtener().create_incident(
                incident_id=incident_id or "",
                raw_text=raw_text,
                title=title,
                created_at=instante,
            )
            return to_incident_created_response(resultado).model_dump(mode="json")

        return _ejecutar(operacion, CREATE_ERROR_INTERNO, "create_incident")

    @mcp.tool()
    def get_active_incidents_summary(
        component: Optional[str] = None,
        reference_time: Optional[str] = None,
    ) -> dict:
        """Resume los incidentes activos y su consumo de SLA, sin modificar datos.

        Funcionamiento:
            Consulta los incidentes en estado activo (`OPEN` o `IN_PROGRESS`),
            calcula para cada uno los minutos consumidos de SLA en el instante
            de referencia y agrega el total y los incumplimientos. Es una
            operación de solo lectura: no crea, resuelve ni actualiza nada. Los
            estados terminales (`RESOLVED`, `CLOSED`) quedan fuera. Úsala para
            responder "qué está abierto ahora", "qué está incumpliendo SLA" o
            "qué carga tiene un componente".

        Args:
            component: Nombre exacto del componente por el que filtrar, por
                ejemplo `payments-gateway`; máximo 128 caracteres. Si es `None`
                o solo espacios se devuelven todos los componentes. El filtro
                es igualdad exacta, no búsqueda parcial ni patrón.
            reference_time: Instante de referencia en ISO 8601 naive con
                separador `T`, `YYYY-MM-DDTHH:MM:SS[.ffffff]` y sin zona
                horaria. Si es `None`, el servicio resuelve el instante actual
                una sola vez y lo aplica a todos los incidentes de la respuesta,
                de modo que el resumen es internamente coherente. Si es anterior
                a la creación de un incidente activo, la operación falla con
                `SUMMARY_REFERENCIA_INCONSISTENTE`.

        Returns:
            Diccionario con `total_active` (número de activos),
            `breached_count` (cuántos incumplen SLA) e `incidents`, una lista
            de objetos con `incident_id`, `title`, `component`, `severity`,
            `status`, `elapsed_minutes`, `is_breached` y
            `requires_escalation`.

        Errores:
            `SUMMARY_COMPONENTE_DEMASIADO_LARGO` si el filtro supera 128
            caracteres; `SUMMARY_REFERENCIA_INVALIDA` si `reference_time` no
            respeta el formato naive; `SUMMARY_REFERENCIA_INCONSISTENTE` (409)
            si la referencia contradice los datos almacenados;
            `CONFIG_DATABASE_URL_INVALIDA` (422) por configuración inválida y
            `SUMMARY_ERROR_INTERNO` (500) ante cualquier otro fallo, incluida
            una base inaccesible.
        """

        def operacion() -> Dict[str, Any]:
            instante = parse_instante_naive(
                reference_time, "reference_time", SUMMARY_REFERENCIA_INVALIDA
            )
            resumen = servicio.obtener().get_active_incidents_summary(
                reference_time=instante,
                component_filter=component,
            )
            return to_summary_response(resumen).model_dump(mode="json")

        return _ejecutar(
            operacion, SUMMARY_ERROR_INTERNO, "get_active_incidents_summary"
        )

    @mcp.tool()
    def evaluate_incident_sla(
        incident_id: str,
        reference_time: Optional[str] = None,
    ) -> dict:
        """Audita el SLA de un incidente almacenado, sin modificar su estado.

        Funcionamiento:
            Recupera el incidente por su identificador y evalúa su SLA en el
            instante de referencia: minutos permitidos según la severidad,
            minutos consumidos (solo dentro de la ventana hábil para P2 y P3),
            minutos restantes, incumplimiento estricto y necesidad de
            escalamiento al 75 % del tiempo permitido. Es una operación de solo
            lectura: no resuelve, cierra ni reasigna el incidente. Úsala para
            auditar un incidente concreto o para explicar por qué está a punto
            de incumplir.

        Args:
            incident_id: Identificador del incidente almacenado, por ejemplo
                `INC-1001`. No puede estar vacío ni contener solo espacios; no
                se admiten búsquedas parciales.
            reference_time: Instante de auditoría en ISO 8601 naive con
                separador `T`, `YYYY-MM-DDTHH:MM:SS[.ffffff]` y sin zona
                horaria. Si es `None`, el servicio usa el instante actual de su
                reloj inyectado. Si es anterior a `created_at`, la operación
                falla con `SLA_REFERENCIA_INCONSISTENTE`.

        Returns:
            Diccionario con `incident_id`, `severity`, `status`, `created_at`,
            `resolved_at`, `reference_time`, `elapsed_minutes`,
            `allowed_minutes`, `remaining_minutes`, `is_breached`,
            `requires_escalation` y `window` (la ventana de cómputo aplicada).

        Errores:
            `SLA_ID_VACIO` si el identificador está vacío;
            `SLA_REFERENCIA_INVALIDA` si la fecha no respeta el formato naive;
            `SLA_INCIDENTE_NO_ENCONTRADO` (404) si no existe un incidente con
            ese identificador; `SLA_REFERENCIA_INCONSISTENTE` (422) si la
            referencia es anterior a la creación; `SLA_DATOS_INCONSISTENTES`
            (409) si el registro almacenado es incoherente;
            `CONFIG_DATABASE_URL_INVALIDA` (422) por configuración inválida y
            `SLA_ERROR_INTERNO` (500) ante cualquier otro fallo, incluida una
            base inaccesible.
        """

        def operacion() -> Dict[str, Any]:
            instante = parse_instante_naive(
                reference_time, "reference_time", SLA_REFERENCIA_INVALIDA
            )
            detalle = servicio.obtener().evaluate_incident_sla(
                incident_id, instante
            )
            return to_sla_evaluation_response(detalle).model_dump(mode="json")

        return _ejecutar(operacion, SLA_ERROR_INTERNO, "evaluate_incident_sla")

    @mcp.tool()
    def check_health() -> dict:
        """Comprueba la conectividad con la base de datos configurada.

        Funcionamiento:
            Ejecuta una comprobación de conectividad mínima (`SELECT 1`) a
            través del caso de uso, sin crear tablas, sin sembrar políticas y
            sin exigir que el esquema exista. Es una operación de solo lectura
            pensada para saber si el servidor puede atender el resto de
            herramientas; no consulta ni modifica incidentes. Una base caída no
            es un error de la herramienta: se informa en el documento de
            respuesta.

        Args:
            Ninguno. La herramienta no recibe parámetros: la base de datos y el
            reloj se resuelven desde la composición del servidor.

        Returns:
            Diccionario con `status` (`ok` si la base responde, `error` si no)
            y `database` (`connected` o `unavailable`). Nunca incluye motor,
            host, usuario, versión, latencia ni la causa del fallo.

        Errores:
            `CONFIG_DATABASE_URL_INVALIDA` (422) si `DATABASE_URL` está vacía,
            usa un esquema no soportado o no indica ruta ni memoria, y
            `HEALTH_ERROR_INTERNO` (500) si la comprobación falla de forma
            inesperada. Una base inaccesible devuelve `status: "error"` en vez
            de lanzar.
        """

        def operacion() -> Dict[str, Any]:
            documento = to_health_response(servicio.obtener().check_health())
            if documento.status != "ok":
                _log("La base de datos configurada no responde.")
            return documento.model_dump(mode="json")

        return _ejecutar(operacion, HEALTH_ERROR_INTERNO, "check_health")

    return mcp


mcp = create_server()


if __name__ == "__main__":
    _log("Iniciando el servidor MCP de IncidentOps sobre transporte stdio.")
    mcp.run()
