"""Pruebas de aceptación del adaptador MCP sobre el caso de uso compartido.

Cada escenario invoca la herramienta por el mismo camino que un cliente MCP
(`MCPServer.call_tool`) sobre un servidor nuevo con repositorio en memoria, de
modo que las pruebas no comparten estado entre sí ni dependen de `DATABASE_URL`.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pytest
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from src.adapters.inbound import mcp_server
from src.adapters.inbound.mcp_server import create_server, mcp
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.services import IncidentService
from src.domain.triage_rules import classify_impact

BASE = "2026-11-20T10:00:00"  # viernes, dentro de la ventana hábil
TEXTO_P0 = "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta."
TEXTO_DUPLICADO = (
    "La pasarela de pagos está caída: ningún comercio puede cobrar con tarjeta."
)
TEXTO_AUTH = "No puedo iniciar sesión en la cuenta, aparece bloqueada."


class _RelojFijo:
    """Doble de `ClockPort` con un instante constante para pruebas deterministas."""

    def __init__(self, instante: datetime) -> None:
        self._instante = instante

    def now(self) -> datetime:
        return self._instante


class _ServicioFalso:
    """Doble mínimo del caso de uso para probar la inyección y la salud."""

    def __init__(self, conectada: bool = True) -> None:
        self.conectada = conectada
        self.llamadas: List[Any] = []

    def triage_incident(self, incident_id: str, raw_text: str) -> Any:
        self.llamadas.append((incident_id, raw_text))
        return classify_impact(incident_id, raw_text)

    def check_health(self) -> bool:
        self.llamadas.append("check_health")
        return self.conectada


def _servidor(servicio: Any = None) -> MCPServer:
    return create_server(servicio)


def _llamar(servidor: MCPServer, nombre: str, argumentos: Dict[str, Any]) -> Dict[str, Any]:
    """Invoca una herramienta y devuelve el JSON de su contenido textual."""
    resultado = asyncio.run(servidor.call_tool(nombre, argumentos))
    return json.loads(resultado.content[0].text)


def _problema(exc: pytest.ExceptionInfo[ToolError]) -> Dict[str, Any]:
    """Extrae el documento problem+json del mensaje de `ToolError`."""
    texto = str(exc.value)
    return json.loads(texto[texto.index("{"):])


def _herramientas(servidor: MCPServer) -> List[Any]:
    async def listar() -> List[Any]:
        return await servidor.list_tools()

    return asyncio.run(listar())


def test_expone_las_cinco_herramientas_con_docstrings_detallados() -> None:
    """El servidor publica las cinco herramientas con descripción extensa."""
    herramientas = _herramientas(_servidor())

    nombres = {herramienta.name for herramienta in herramientas}
    assert nombres == {
        "triage_incident",
        "create_incident",
        "get_active_incidents_summary",
        "evaluate_incident_sla",
        "check_health",
    }

    for herramienta in herramientas:
        descripcion = herramienta.description or ""
        assert len(descripcion) > 400, herramienta.name
        for seccion in ("Funcionamiento:", "Args:", "Returns:", "Errores:"):
            assert seccion in descripcion, herramienta.name


def test_el_servidor_de_modulo_no_construye_el_servicio_al_importar() -> None:
    """El `mcp` de módulo arranca sin depender de `DATABASE_URL`."""
    assert isinstance(mcp, MCPServer)
    assert {h.name for h in _herramientas(mcp)} == {
        "triage_incident",
        "create_incident",
        "get_active_incidents_summary",
        "evaluate_incident_sla",
        "check_health",
    }


def test_triaje_clasifica_sin_persistir() -> None:
    """Dado un reporte de pagos, Cuando se tria, Entonces clasifica sin guardar."""
    servidor = _servidor()

    triaje = _llamar(
        servidor,
        "triage_incident",
        {"incident_id": "INC-1", "raw_text": TEXTO_P0},
    )

    assert triaje["severity"] == "P0"
    assert triaje["component"] == "payments-gateway"
    assert triaje["recommended_team"] == "Backend-Core"
    assert triaje["duplicate_group_key"] is None
    # No hay alta: el resumen sigue vacío.
    resumen = _llamar(servidor, "get_active_incidents_summary", {})
    assert resumen["total_active"] == 0


def test_triaje_rechaza_identificador_vacio() -> None:
    """Un identificador vacío produce TRIAGE_ID_VACIO con estado 422."""
    with pytest.raises(ToolError) as info:
        _llamar(
            _servidor(),
            "triage_incident",
            {"incident_id": "   ", "raw_text": TEXTO_P0},
        )

    problema = _problema(info)
    assert problema["code"] == "TRIAGE_ID_VACIO"
    assert problema["status"] == 422
    assert problema["errors"][0]["field"] == "incident_id"


def test_alta_persiste_y_el_resumen_la_incluye() -> None:
    """Dado un alta válida, Cuando se resume, Entonces aparece como activa."""
    servidor = _servidor()

    creado = _llamar(
        servidor,
        "create_incident",
        {
            "title": "Pagos caídos",
            "raw_text": TEXTO_P0,
            "incident_id": "INC-1",
            "created_at": BASE,
        },
    )
    assert creado["status"] == "OPEN"
    assert creado["is_duplicate"] is False
    assert creado["duplicate_of"] == []
    assert creado["created_at"].startswith(BASE)

    resumen = _llamar(
        servidor,
        "get_active_incidents_summary",
        {"reference_time": "2026-11-20T11:00:00"},
    )
    assert resumen["total_active"] == 1
    assert resumen["incidents"][0]["incident_id"] == "INC-1"
    assert resumen["incidents"][0]["elapsed_minutes"] == 60


def test_alta_sin_identificador_se_rechaza() -> None:
    """`incident_id` omitido no se inventa: se rechaza con CREATE_ID_VACIO."""
    with pytest.raises(ToolError) as info:
        _llamar(
            _servidor(),
            "create_incident",
            {"title": "Pagos caídos", "raw_text": TEXTO_P0},
        )

    problema = _problema(info)
    assert problema["code"] == "CREATE_ID_VACIO"
    assert problema["status"] == 422


def test_alta_rechaza_identificador_duplicado() -> None:
    """Un segundo alta con el mismo identificador devuelve CREATE_ID_CONFLICTO."""
    servidor = _servidor()
    argumentos = {
        "title": "Pagos caídos",
        "raw_text": TEXTO_P0,
        "incident_id": "INC-1",
        "created_at": BASE,
    }
    _llamar(servidor, "create_incident", argumentos)

    with pytest.raises(ToolError) as info:
        _llamar(servidor, "create_incident", argumentos)

    problema = _problema(info)
    assert problema["code"] == "CREATE_ID_CONFLICTO"
    assert problema["status"] == 409


def test_alta_rechaza_fecha_invalida() -> None:
    """Una fecha sin separador `T` se rechaza con CREATE_CREACION_INVALIDA."""
    with pytest.raises(ToolError) as info:
        _llamar(
            _servidor(),
            "create_incident",
            {
                "title": "Pagos caídos",
                "raw_text": TEXTO_P0,
                "incident_id": "INC-1",
                "created_at": "2026-11-20 10:00:00",
            },
        )

    problema = _problema(info)
    assert problema["code"] == "CREATE_CREACION_INVALIDA"
    assert problema["status"] == 422


def test_alta_avisa_de_duplicado_sin_modificar_el_original() -> None:
    """Dos reportes equivalentes activos marcan el segundo como duplicado."""
    servidor = _servidor()
    _llamar(
        servidor,
        "create_incident",
        {
            "title": "Pagos caídos",
            "raw_text": TEXTO_P0,
            "incident_id": "INC-A",
            "created_at": BASE,
        },
    )

    segundo = _llamar(
        servidor,
        "create_incident",
        {
            "title": "Pagos caídos (aviso)",
            "raw_text": TEXTO_DUPLICADO,
            "incident_id": "INC-B",
            "created_at": "2026-11-20T10:05:00",
        },
    )

    assert segundo["is_duplicate"] is True
    assert segundo["duplicate_group_key"] == "INC-A"
    assert segundo["duplicate_of"] == ["INC-A"]

    resumen = _llamar(
        servidor,
        "get_active_incidents_summary",
        {"reference_time": "2026-11-20T11:00:00"},
    )
    assert resumen["total_active"] == 2


def test_resumen_filtra_por_componente() -> None:
    """El filtro de componente es igualdad exacta y descarta el resto."""
    servidor = _servidor()
    for incident_id, texto in (("INC-1", TEXTO_P0), ("INC-2", TEXTO_AUTH)):
        _llamar(
            servidor,
            "create_incident",
            {
                "title": f"Reporte {incident_id}",
                "raw_text": texto,
                "incident_id": incident_id,
                "created_at": BASE,
            },
        )

    resumen = _llamar(
        servidor,
        "get_active_incidents_summary",
        {"component": "auth-identity", "reference_time": "2026-11-20T11:00:00"},
    )

    assert resumen["total_active"] == 1
    assert resumen["incidents"][0]["incident_id"] == "INC-2"


def test_resumen_rechaza_referencia_invalida() -> None:
    """Una referencia con zona horaria se rechaza con SUMMARY_REFERENCIA_INVALIDA."""
    with pytest.raises(ToolError) as info:
        _llamar(
            _servidor(),
            "get_active_incidents_summary",
            {"reference_time": "2026-11-20T12:00:00+00:00"},
        )

    assert _problema(info)["code"] == "SUMMARY_REFERENCIA_INVALIDA"


def test_sla_audita_un_incidente_existente() -> None:
    """Un P0 creado dos horas antes del límite aparece incumplido."""
    servidor = _servidor()
    _llamar(
        servidor,
        "create_incident",
        {
            "title": "Pagos caídos",
            "raw_text": TEXTO_P0,
            "incident_id": "INC-1",
            "created_at": BASE,
        },
    )

    detalle = _llamar(
        servidor,
        "evaluate_incident_sla",
        {"incident_id": "INC-1", "reference_time": "2026-11-20T12:00:00"},
    )

    assert detalle["severity"] == "P0"
    assert detalle["elapsed_minutes"] == 120
    assert detalle["allowed_minutes"] == 60
    assert detalle["remaining_minutes"] == -60
    assert detalle["is_breached"] is True
    assert detalle["requires_escalation"] is False
    assert detalle["window"] == "24x7"


def test_sla_de_incidente_inexistente_devuelve_404() -> None:
    """Un identificador desconocido produce SLA_INCIDENTE_NO_ENCONTRADO (404)."""
    with pytest.raises(ToolError) as info:
        _llamar(
            _servidor(),
            "evaluate_incident_sla",
            {"incident_id": "INC-404"},
        )

    problema = _problema(info)
    assert problema["code"] == "SLA_INCIDENTE_NO_ENCONTRADO"
    assert problema["status"] == 404


def test_salud_informa_base_disponible() -> None:
    """Con la base en memoria, la salud devuelve ok/connected."""
    assert _llamar(_servidor(), "check_health", {}) == {
        "status": "ok",
        "database": "connected",
    }


def test_salud_informa_base_caida_sin_lanzar() -> None:
    """Una base inaccesible se informa en el documento, no como error."""
    documento = _llamar(_servidor(_ServicioFalso(conectada=False)), "check_health", {})

    assert documento == {"status": "error", "database": "unavailable"}


def test_inyecta_el_caso_de_uso_recibido() -> None:
    """El servidor usa el servicio inyectado y no la fábrica."""
    falso = _ServicioFalso()

    triaje = _llamar(
        _servidor(falso),
        "triage_incident",
        {"incident_id": "INC-1", "raw_text": TEXTO_P0},
    )

    assert triaje["severity"] == "P0"
    assert falso.llamadas == [("INC-1", TEXTO_P0)]


def test_stdout_permanece_limpio(capsys: "pytest.CaptureFixture[str]") -> None:
    """Las herramientas escriben diagnóstico solo en stderr."""
    servidor = _servidor()

    _llamar(
        servidor,
        "create_incident",
        {
            "title": "Pagos caídos",
            "raw_text": TEXTO_P0,
            "incident_id": "INC-1",
            "created_at": BASE,
        },
    )
    _llamar(servidor, "check_health", {})

    capturado = capsys.readouterr()
    assert capturado.out == ""
    assert "[mcp]" in capturado.err


# ---------------------------------------------------------------------------
# US5 · Reutilización del caso de uso y serialización limpia
# ---------------------------------------------------------------------------


def test_funciones_mcp_con_repositorio_en_memoria() -> None:
    """Las cinco herramientas operan sobre IncidentService y SQLite en memoria.

    Dado un caso de uso compuesto explícitamente con `SQLiteIncidentRepository`
    en memoria y un reloj fijo, Cuando se invocan las herramientas sin fechas,
    Entonces usan ese reloj, persisten en ese repositorio y devuelven documentos
    JSON con la misma forma que el CLI.
    """
    repositorio = SQLiteIncidentRepository(":memory:")
    reloj = _RelojFijo(datetime(2026, 11, 20, 11, 0, 0))
    servidor = create_server(IncidentService(repositorio, clock=reloj))

    triaje = _llamar(
        servidor,
        "triage_incident",
        {"incident_id": "INC-1", "raw_text": TEXTO_P0},
    )
    assert triaje["severity"] == "P0"
    assert repositorio.get_incident("INC-1") is None

    creado = _llamar(
        servidor,
        "create_incident",
        {"title": "Pagos caídos", "raw_text": TEXTO_P0, "incident_id": "INC-1"},
    )
    assert creado["created_at"] == "2026-11-20T11:00:00"
    assert repositorio.get_incident("INC-1") is not None

    resumen = _llamar(servidor, "get_active_incidents_summary", {})
    assert resumen["total_active"] == 1
    assert resumen["incidents"][0]["elapsed_minutes"] == 0

    detalle = _llamar(servidor, "evaluate_incident_sla", {"incident_id": "INC-1"})
    assert detalle["reference_time"] == "2026-11-20T11:00:00"
    assert detalle["is_breached"] is False

    assert _llamar(servidor, "check_health", {}) == {
        "status": "ok",
        "database": "connected",
    }


def test_serializacion_json_identica_al_cli() -> None:
    """El texto devuelto es el mismo JSON limpio que escribe la CLI.

    La CLI serializa con `json.dumps(..., ensure_ascii=False, indent=2)`; el
    servidor MCP entrega un diccionario y el SDK aplica exactamente ese formato.
    Se comprueba el contenido y la ausencia de escapes `\\u`.
    """
    servidor = _servidor()
    resultado = asyncio.run(
        servidor.call_tool(
            "create_incident",
            {
                "title": "Pagos caídos en producción",
                "raw_text": TEXTO_P0,
                "incident_id": "INC-1",
                "created_at": BASE,
            },
        )
    )
    texto = resultado.content[0].text
    documento = json.loads(texto)

    assert json.dumps(documento, ensure_ascii=False, indent=2) == texto
    assert "\\u" not in texto
    assert "caídos" in texto
    assert documento["created_at"].startswith("2026-11-20T10:00:00")
    assert isinstance(documento["duplicate_of"], list)


def test_cada_parametro_esta_documentado_en_los_args() -> None:
    """Toda entrada del esquema aparece descrita en la sección `Args`."""
    for herramienta in _herramientas(_servidor()):
        propiedades = (herramienta.input_schema or {}).get("properties", {})
        if not propiedades:
            continue
        descripcion = herramienta.description or ""
        bloque = descripcion[descripcion.index("Args:"):descripcion.index("Returns:")]
        for parametro in propiedades:
            assert parametro in bloque, (herramienta.name, parametro)


def test_modulo_sin_print_y_sin_persistencia_concreta() -> None:
    """El adaptador no usa `print` ni importa drivers: solo la fábrica."""
    fuente = Path(mcp_server.__file__).read_text(encoding="utf-8")

    assert "print(" not in fuente
    assert "sys.stderr.write" in fuente
    assert "from src.adapters.outbound.factory import" in fuente
    for modulo in ("sqlite3", "psycopg", "pgvector", "langgraph"):
        assert f"import {modulo}" not in fuente
        assert f"from {modulo}" not in fuente
