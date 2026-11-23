"""Pruebas de aceptación BDD de H003: ciclo de vida, duplicados y SLA.

Cada escenario sigue Dado / Cuando / Entonces (Constitución §VII) y atraviesa
los dos adaptadores de entrada sobre una base SQLite de archivo temporal. La
paridad HTTP/CLI se verifica por igualdad estricta de documentos JSON.
"""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import app as cli_app
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.services import IncidentService
from src.domain.models import Incident

RUTA_ALTA = "/api/v1/incidents"
RUTA_RESUMEN = "/api/v1/incidents/summary"
RUTA_SLA = "/api/v1/incidents/{incident_id}/sla"

BASE = datetime(2026, 11, 20, 10, 0, 0)  # viernes
TEXTO_P0 = "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta."
TEXTO_DUPLICADO = (
    "La pasarela de pagos está caída: ningún comercio puede cobrar con tarjeta."
)
TEXTO_P1 = "Timeout en el pool de conexiones de PostgreSQL."
TEXTO_P2 = "La base de datos PostgreSQL está lenta, consultas de 12 segundos."


def _iso(instante: datetime) -> str:
    return instante.isoformat()


@pytest.fixture()
def base_temporal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Archivo SQLite aislado con `DATABASE_URL` apuntando a él."""
    ruta = tmp_path / "ciclo-vida.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{ruta}")
    return ruta


def _error(resultado: Any) -> str:
    return (resultado.stderr or "") + (resultado.output or "")


def _alta_http(cliente: TestClient, **payload: Any) -> Any:
    return cliente.post(RUTA_ALTA, json=payload)


def _alta_ok(cliente: TestClient, **payload: Any) -> Dict[str, Any]:
    respuesta = _alta_http(cliente, **payload)
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _sla_http(
    cliente: TestClient,
    incident_id: str,
    reference_time: Optional[str] = None,
) -> Dict[str, Any]:
    parametros = {} if reference_time is None else {"reference_time": reference_time}
    respuesta = cliente.get(
        RUTA_SLA.format(incident_id=incident_id), params=parametros
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _alta_cli(runner: CliRunner, *argumentos: str) -> Dict[str, Any]:
    salida = runner.invoke(cli_app, ["create", *argumentos])
    assert salida.exit_code == 0, _error(salida)
    return json.loads(salida.stdout)


def _sla_cli(runner: CliRunner, *argumentos: str) -> Dict[str, Any]:
    salida = runner.invoke(cli_app, ["sla", *argumentos])
    assert salida.exit_code == 0, _error(salida)
    return json.loads(salida.stdout)


def _sembrar(ruta: Path, incidentes: List[Incident]) -> None:
    repositorio = SQLiteIncidentRepository(str(ruta))
    for incidente in incidentes:
        repositorio.save_incident(incidente)


def _sembrado(
    incident_id: str,
    component: str = "payments-gateway",
    severity: str = "P0",
    status: str = "OPEN",
    created_at: datetime = BASE,
    resolved_at: Optional[datetime] = None,
    raw_text: Optional[str] = TEXTO_DUPLICADO,
    duplicate_group_key: Optional[str] = None,
) -> Incident:
    return Incident(
        incident_id=incident_id,
        title=f"Incidente {incident_id}",
        component=component,
        severity=severity,
        status=status,
        created_at=created_at,
        resolved_at=resolved_at,
        raw_text=raw_text,
        recommended_team=None,
        duplicate_group_key=duplicate_group_key,
    )


# ---------------------------------------------------------------------------
# US1 · Alta persistente de incidentes
# ---------------------------------------------------------------------------


def test_us1_alta_http_clasifica_y_persiste_en_open(base_temporal: Path) -> None:
    """Dado un reporte nuevo, Cuando se registra, Entonces 201 con clasificación."""
    cliente = TestClient(create_app())

    cuerpo = _alta_ok(
        cliente,
        incident_id="INC-3001",
        raw_text=TEXTO_P0,
        created_at=_iso(BASE),
    )

    assert cuerpo == {
        "incident_id": "INC-3001",
        "title": TEXTO_P0,
        "component": "payments-gateway",
        "severity": "P0",
        "recommended_team": "Backend-Core",
        "status": "OPEN",
        "created_at": "2026-11-20T10:00:00",
        "resolved_at": None,
        "duplicate_group_key": None,
        "is_duplicate": False,
        "duplicate_of": [],
    }
    persistido = SQLiteIncidentRepository(str(base_temporal)).get_incident("INC-3001")
    assert persistido is not None
    assert persistido.raw_text == TEXTO_P0
    assert persistido.recommended_team == "Backend-Core"
    assert persistido.status == "OPEN"


def test_us1_titulo_derivado_de_la_primera_linea_con_maximo_200(
    base_temporal: Path,
) -> None:
    """FR-007: el título omitido se deriva de la primera línea y no supera 200."""
    cliente = TestClient(create_app())
    primera_linea = "Título " + "x" * 300

    cuerpo = _alta_ok(
        cliente,
        incident_id="INC-3001",
        raw_text=f"{primera_linea}\nDetalle adicional del reporte.",
        created_at=_iso(BASE),
    )

    assert cuerpo["title"] == primera_linea[:200]
    assert len(cuerpo["title"]) == 200


def test_us1_alta_por_cli_y_recuperacion_tras_reinicio(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """Dado un alta por consola, Cuando el proceso reinicia, Entonces sigue igual."""
    registrado = _alta_cli(
        runner_cli,
        "--incident-id",
        "INC-3002",
        "--raw-text",
        TEXTO_P0,
        "--created-at",
        "2026-11-20T10:05:00",
    )

    tras_reinicio = SQLiteIncidentRepository(str(base_temporal)).get_incident("INC-3002")

    assert tras_reinicio is not None
    assert tras_reinicio.incident_id == registrado["incident_id"]
    assert tras_reinicio.title == registrado["title"]
    assert tras_reinicio.component == registrado["component"]
    assert tras_reinicio.severity == registrado["severity"]
    assert tras_reinicio.status == registrado["status"]
    assert tras_reinicio.created_at.isoformat() == registrado["created_at"]
    assert tras_reinicio.raw_text == TEXTO_P0


def test_us1_el_registrado_aparece_una_sola_vez_en_el_resumen(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """SC-009: el resumen refleja identificador, título, componente, severidad y estado."""
    _alta_cli(
        runner_cli,
        "--incident-id",
        "INC-3003",
        "--raw-text",
        TEXTO_P0,
        "--created-at",
        "2026-11-20T10:05:00",
    )
    cliente = TestClient(create_app())

    respuesta = cliente.get(
        RUTA_RESUMEN, params={"reference_time": "2026-11-20T12:00:00"}
    )

    assert respuesta.status_code == 200, respuesta.text
    incidentes = respuesta.json()["incidents"]
    coincidencias = [
        item for item in incidentes if item["incident_id"] == "INC-3003"
    ]
    assert len(coincidencias) == 1
    assert coincidencias[0]["title"] == TEXTO_P0
    assert coincidencias[0]["component"] == "payments-gateway"
    assert coincidencias[0]["severity"] == "P0"
    assert coincidencias[0]["status"] == "OPEN"


def test_us1_conflicto_de_identificador_es_conflicto_sin_sobrescribir(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """FR-008: repetir el identificador es 409 por HTTP y salida 1 por consola."""
    cliente = TestClient(create_app())
    original = _alta_ok(
        cliente, incident_id="INC-3004", raw_text=TEXTO_P0, created_at=_iso(BASE)
    )

    respuesta = _alta_http(
        cliente,
        incident_id="INC-3004",
        raw_text="Otro texto completamente distinto.",
        created_at=_iso(BASE + timedelta(hours=1)),
    )

    assert respuesta.status_code == 409
    assert respuesta.headers["content-type"].startswith("application/problem+json")
    assert respuesta.json()["code"] == "CREATE_ID_CONFLICTO"
    assert "is_duplicate" not in respuesta.json()

    salida = runner_cli.invoke(
        cli_app,
        [
            "create",
            "--incident-id",
            "INC-3004",
            "--raw-text",
            "Otro texto completamente distinto.",
            "--created-at",
            "2026-11-20T11:00:00",
        ],
    )
    assert salida.exit_code == 1
    assert salida.stdout.strip() == ""
    assert "CREATE_ID_CONFLICTO" in _error(salida)

    persistido = SQLiteIncidentRepository(str(base_temporal)).get_incident("INC-3004")
    assert persistido is not None
    assert persistido.raw_text == TEXTO_P0
    assert persistido.title == original["title"]
    assert persistido.created_at == BASE


@pytest.mark.parametrize(
    ("payload", "codigo"),
    [
        ({"incident_id": "", "raw_text": TEXTO_P0}, "CREATE_ID_VACIO"),
        ({"incident_id": "   ", "raw_text": TEXTO_P0}, "CREATE_ID_VACIO"),
        ({"incident_id": "I" * 65, "raw_text": TEXTO_P0}, "CREATE_ID_DEMASIADO_LARGO"),
        ({"incident_id": "INC-1", "raw_text": "   "}, "CREATE_TEXTO_VACIO"),
        ({"incident_id": "INC-1", "raw_text": "a" * 10_001}, "CREATE_TEXTO_DEMASIADO_LARGO"),
    ],
)
def test_us1_entradas_invalidas_son_422_y_salida_2(
    base_temporal: Path,
    runner_cli: CliRunner,
    payload: Dict[str, str],
    codigo: str,
) -> None:
    """FR-009: identificador o texto inválidos no persisten nada."""
    cliente = TestClient(create_app())

    respuesta = _alta_http(cliente, **payload)

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == codigo
    assert "incident_id" not in respuesta.json() or "title" not in respuesta.json()

    salida = runner_cli.invoke(
        cli_app,
        [
            "create",
            "--incident-id",
            payload["incident_id"],
            "--raw-text",
            payload["raw_text"],
        ],
    )
    assert salida.exit_code == 2
    assert salida.stdout.strip() == ""
    assert codigo in _error(salida)
    assert SQLiteIncidentRepository(str(base_temporal)).get_incident("INC-1") is None


@pytest.mark.parametrize(
    "created_at",
    [
        "2026-11-20 10:00:00",
        "2026-11-20T10:00:00+00:00",
        "no-es-fecha",
    ],
)
def test_us1_created_at_invalido_es_422_y_salida_2(
    base_temporal: Path, runner_cli: CliRunner, created_at: str
) -> None:
    """FR-024: fecha con espacio, con zona o ilegible se rechaza sin persistir."""
    cliente = TestClient(create_app())

    respuesta = _alta_http(
        cliente, incident_id="INC-1", raw_text=TEXTO_P0, created_at=created_at
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "CREATE_CREACION_INVALIDA"
    assert "is_duplicate" not in respuesta.json()

    salida = runner_cli.invoke(
        cli_app,
        [
            "create",
            "--incident-id",
            "INC-1",
            "--raw-text",
            TEXTO_P0,
            "--created-at",
            created_at,
        ],
    )
    assert salida.exit_code == 2
    assert salida.stdout.strip() == ""
    assert "CREATE_CREACION_INVALIDA" in _error(salida)
    assert SQLiteIncidentRepository(str(base_temporal)).get_incident("INC-1") is None


# ---------------------------------------------------------------------------
# US2 · Aviso de duplicados abiertos
# ---------------------------------------------------------------------------


def test_us2_aviso_simple_en_la_misma_respuesta(base_temporal: Path) -> None:
    """Dado un original activo, Cuando llega un equivalente, Entonces avisa."""
    cliente = TestClient(create_app())
    _alta_ok(
        cliente, incident_id="INC-A", raw_text=TEXTO_P0, created_at=_iso(BASE)
    )

    cuerpo = _alta_ok(
        cliente,
        incident_id="INC-B",
        raw_text=TEXTO_DUPLICADO,
        created_at=_iso(BASE + timedelta(minutes=5)),
    )

    assert cuerpo["is_duplicate"] is True
    assert cuerpo["duplicate_of"] == ["INC-A"]
    assert cuerpo["duplicate_group_key"] == "INC-A"
    assert cuerpo["status"] == "OPEN"

    original = SQLiteIncidentRepository(str(base_temporal)).get_incident("INC-A")
    assert original is not None
    assert original.duplicate_group_key is None
    assert original.raw_text == TEXTO_P0


@pytest.mark.parametrize(
    "caso",
    ["terminal", "otro_componente", "similitud", "ventana", "sin_texto"],
)
def test_us2_sin_falsos_positivos(base_temporal: Path, caso: str) -> None:
    """SC-002: ninguna variante límite produce un aviso de duplicado."""
    candidato = _sembrado("INC-CAND")
    if caso == "terminal":
        candidato = _sembrado(
            "INC-CAND",
            status="RESOLVED",
            resolved_at=BASE + timedelta(minutes=20),
        )
    elif caso == "otro_componente":
        candidato = _sembrado("INC-CAND", component="auth-identity")
    elif caso == "similitud":
        candidato = _sembrado("INC-CAND", raw_text="pago " + "a" * 400)
    elif caso == "ventana":
        candidato = _sembrado("INC-CAND", created_at=BASE - timedelta(days=2))
    elif caso == "sin_texto":
        candidato = _sembrado("INC-CAND", raw_text=None)
    _sembrar(base_temporal, [candidato])
    cliente = TestClient(create_app())

    texto_nuevo = "pago " + "b" * 400 if caso == "similitud" else TEXTO_P0
    cuerpo = _alta_ok(
        cliente,
        incident_id="INC-NUEVO",
        raw_text=texto_nuevo,
        created_at=_iso(BASE),
    )

    assert cuerpo["is_duplicate"] is False
    assert cuerpo["duplicate_of"] == []
    assert cuerpo["duplicate_group_key"] is None


def test_us2_hereda_la_clave_del_original(base_temporal: Path) -> None:
    """FR-014: la clave es la del original y nunca la de un duplicado intermedio."""
    _sembrar(
        base_temporal,
        [
            _sembrado("INC-A", duplicate_group_key="INC-ORIG"),
            _sembrado(
                "INC-B",
                created_at=BASE + timedelta(minutes=1),
                duplicate_group_key="INC-ORIG",
            ),
        ],
    )
    cliente = TestClient(create_app())

    cuerpo = _alta_ok(
        cliente,
        incident_id="INC-C",
        raw_text=TEXTO_DUPLICADO,
        created_at=_iso(BASE + timedelta(minutes=2)),
    )

    assert cuerpo["duplicate_group_key"] == "INC-ORIG"
    assert cuerpo["duplicate_of"] == ["INC-A", "INC-B"]


def test_us2_el_nuevo_mas_antiguo_actua_como_original(base_temporal: Path) -> None:
    """US2 caso límite: el nuevo más antiguo no recibe clave ni se marca duplicado."""
    _sembrar(
        base_temporal,
        [_sembrado("INC-POST", created_at=BASE + timedelta(minutes=1))],
    )
    cliente = TestClient(create_app())

    cuerpo = _alta_ok(
        cliente, incident_id="INC-PRE", raw_text=TEXTO_P0, created_at=_iso(BASE)
    )

    assert cuerpo["is_duplicate"] is False
    assert cuerpo["duplicate_of"] == []
    assert cuerpo["duplicate_group_key"] is None
    posterior = SQLiteIncidentRepository(str(base_temporal)).get_incident("INC-POST")
    assert posterior is not None
    assert posterior.duplicate_group_key is None


def test_us2_duplicate_of_ordenado_y_sin_fusionar(base_temporal: Path) -> None:
    """FR-013/FR-015: orden canónico y previos intactos tras el aviso."""
    previos = [
        _sembrado("INC-Z", created_at=BASE),
        _sembrado("INC-A", created_at=BASE + timedelta(minutes=5)),
        _sembrado("INC-M", created_at=BASE + timedelta(minutes=10)),
    ]
    _sembrar(base_temporal, previos)
    repositorio = SQLiteIncidentRepository(str(base_temporal))
    antes = [repositorio.get_incident(previo.incident_id) for previo in previos]
    cliente = TestClient(create_app())

    cuerpo = _alta_ok(
        cliente,
        incident_id="INC-NUEVO",
        raw_text=TEXTO_DUPLICADO,
        created_at=_iso(BASE + timedelta(minutes=15)),
    )

    assert cuerpo["duplicate_of"] == ["INC-Z", "INC-A", "INC-M"]
    despues = [repositorio.get_incident(previo.incident_id) for previo in previos]
    assert despues == antes


def test_us2_concurrencia_serializada_por_componente(base_temporal: Path) -> None:
    """SC-010: dos altas concurrentes se serializan, ambas persisten y la
    segunda en confirmarse ve a la primera.

    El orden de confirmación depende del planificador, así que la aserción se
    hace sobre el orden realmente observado en el puerto de escritura: si el
    incidente canónicamente más reciente se confirma segundo, informa al
    primero; si lo hace primero, el más antiguo no inventa un duplicado
    posterior.
    """
    interno = SQLiteIncidentRepository(str(base_temporal))

    class _RepositorioConOrden:
        def __init__(self) -> None:
            self.orden: List[str] = []
            self._guarda = threading.Lock()

        def save_incident(self, incident: Incident) -> None:
            interno.save_incident(incident)
            with self._guarda:
                self.orden.append(incident.incident_id)

        def __getattr__(self, nombre: str) -> Any:
            return getattr(interno, nombre)

    repositorio = _RepositorioConOrden()
    servicio = IncidentService(repositorio)
    barrera = threading.Barrier(2)
    resultados: Dict[str, Any] = {}
    errores: List[BaseException] = []

    def alta(incident_id: str, created_at: datetime, texto: str) -> None:
        try:
            barrera.wait(timeout=10)
            resultados[incident_id] = servicio.create_incident(
                incident_id, texto, created_at=created_at
            )
        except BaseException as exc:  # noqa: BLE001 - se reporta en el hilo principal
            errores.append(exc)

    hilos = [
        threading.Thread(
            target=alta, args=("INC-DUPA", BASE, TEXTO_P0)
        ),
        threading.Thread(
            target=alta,
            args=("INC-DUPB", BASE + timedelta(minutes=1), TEXTO_DUPLICADO),
        ),
    ]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=10)

    assert errores == []
    assert set(repositorio.orden) == {"INC-DUPA", "INC-DUPB"}
    assert interno.get_incident("INC-DUPA") is not None
    assert interno.get_incident("INC-DUPB") is not None

    if repositorio.orden[1] == "INC-DUPB":
        assert resultados["INC-DUPB"].duplicate.duplicate_of == ("INC-DUPA",)
        assert resultados["INC-DUPB"].incident.duplicate_group_key == "INC-DUPA"
    else:
        assert resultados["INC-DUPA"].duplicate.is_duplicate is False


# ---------------------------------------------------------------------------
# US3 · Auditoría de SLA de un incidente concreto
# ---------------------------------------------------------------------------


def test_us3_sla_activo_con_contexto_completo(base_temporal: Path) -> None:
    """FR-018: el documento informa el contexto y la ventana aplicada."""
    cliente = TestClient(create_app())
    _alta_ok(cliente, incident_id="INC-3001", raw_text=TEXTO_P0, created_at=_iso(BASE))

    cuerpo = _sla_http(cliente, "INC-3001", "2026-11-20T10:45:00")

    assert cuerpo == {
        "incident_id": "INC-3001",
        "severity": "P0",
        "status": "OPEN",
        "created_at": "2026-11-20T10:00:00",
        "resolved_at": None,
        "reference_time": "2026-11-20T10:45:00",
        "elapsed_minutes": 45,
        "allowed_minutes": 60,
        "remaining_minutes": 15,
        "is_breached": False,
        "requires_escalation": True,
        "window": "24x7",
    }


@pytest.mark.parametrize(
    ("minutos", "incumplido", "restantes", "escala"),
    [(60, False, 0, True), (61, True, -1, False)],
)
def test_us3_fronteras_p0_60_y_61(
    base_temporal: Path,
    minutos: int,
    incumplido: bool,
    restantes: int,
    escala: bool,
) -> None:
    """SC-005: el límite exacto no incumple; un minuto más sí."""
    cliente = TestClient(create_app())
    _alta_ok(cliente, incident_id="INC-3001", raw_text=TEXTO_P0, created_at=_iso(BASE))

    cuerpo = _sla_http(
        cliente, "INC-3001", _iso(BASE + timedelta(minutes=minutos))
    )

    assert cuerpo["elapsed_minutes"] == minutos
    assert cuerpo["remaining_minutes"] == restantes
    assert cuerpo["is_breached"] is incumplido
    assert cuerpo["requires_escalation"] is escala


def test_us3_p1_con_180_minutos_requiere_escalamiento(base_temporal: Path) -> None:
    """SC-005: 180 minutos es el 75 % de P1 y debe escalar."""
    cliente = TestClient(create_app())
    _alta_ok(cliente, incident_id="INC-P1", raw_text=TEXTO_P1, created_at=_iso(BASE))

    cuerpo = _sla_http(cliente, "INC-P1", _iso(BASE + timedelta(minutes=180)))

    assert cuerpo["severity"] == "P1"
    assert cuerpo["allowed_minutes"] == 240
    assert cuerpo["elapsed_minutes"] == 180
    assert cuerpo["requires_escalation"] is True
    assert cuerpo["is_breached"] is False


def test_us3_p2_de_viernes_a_lunes_excluye_el_fin_de_semana(
    base_temporal: Path,
) -> None:
    """SC-005: P2 viernes 17:00 → lunes 09:00 son 120 minutos hábiles."""
    cliente = TestClient(create_app())
    _alta_ok(
        cliente,
        incident_id="INC-P2",
        raw_text=TEXTO_P2,
        created_at="2026-11-06T17:00:00",
    )

    cuerpo = _sla_http(cliente, "INC-P2", "2026-11-09T09:00:00")

    assert cuerpo["severity"] == "P2"
    assert cuerpo["elapsed_minutes"] == 120
    assert cuerpo["allowed_minutes"] == 480
    assert cuerpo["remaining_minutes"] == 360
    assert cuerpo["is_breached"] is False
    assert cuerpo["requires_escalation"] is False
    assert cuerpo["window"] == "BUSINESS_HOURS"


@pytest.mark.parametrize(
    "referencia", ["2026-11-20T10:10:00", "2026-11-25T10:10:00"]
)
def test_us3_terminal_congelado_antes_y_despues_de_la_resolucion(
    base_temporal: Path, referencia: str
) -> None:
    """FR-026: el cómputo se detiene en `resolved_at` y no crece ni retrocede."""
    _sembrar(
        base_temporal,
        [
            _sembrado(
                "INC-RES",
                status="RESOLVED",
                created_at=BASE,
                resolved_at=BASE + timedelta(minutes=30),
            )
        ],
    )
    cliente = TestClient(create_app())

    cuerpo = _sla_http(cliente, "INC-RES", referencia)

    assert cuerpo["elapsed_minutes"] == 30
    assert cuerpo["resolved_at"] == "2026-11-20T10:30:00"
    assert cuerpo["requires_escalation"] is False


def test_us3_referencia_anterior_a_la_creacion_es_422_y_salida_1(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """FR-022: referencia incoherente sin minutos negativos ni documento parcial."""
    cliente = TestClient(create_app())
    _alta_ok(cliente, incident_id="INC-3001", raw_text=TEXTO_P0, created_at=_iso(BASE))

    respuesta = cliente.get(
        RUTA_SLA.format(incident_id="INC-3001"),
        params={"reference_time": "2026-11-20T09:59:59"},
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "SLA_REFERENCIA_INCONSISTENTE"
    assert "elapsed_minutes" not in respuesta.json()

    salida = runner_cli.invoke(
        cli_app,
        [
            "sla",
            "--incident-id",
            "INC-3001",
            "--reference-time",
            "2026-11-20T09:59:59",
        ],
    )
    assert salida.exit_code == 1
    assert salida.stdout.strip() == ""
    assert "SLA_REFERENCIA_INCONSISTENTE" in _error(salida)


def test_us3_incidente_inexistente_es_404_y_salida_1(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """FR-023: un identificador desconocido es 404 y código de salida 1."""
    cliente = TestClient(create_app())

    respuesta = cliente.get(RUTA_SLA.format(incident_id="INC-9999"))

    assert respuesta.status_code == 404
    assert respuesta.json()["code"] == "SLA_INCIDENTE_NO_ENCONTRADO"
    assert "elapsed_minutes" not in respuesta.json()

    salida = runner_cli.invoke(cli_app, ["sla", "--incident-id", "INC-9999"])
    assert salida.exit_code == 1
    assert salida.stdout.strip() == ""
    assert "SLA_INCIDENTE_NO_ENCONTRADO" in _error(salida)


def test_us3_referencia_omitida_informa_el_instante_aplicado(
    base_temporal: Path,
) -> None:
    """FR-017: sin `reference_time` se aplica el instante actual y se informa."""
    cliente = TestClient(create_app())
    _alta_ok(
        cliente,
        incident_id="INC-3001",
        raw_text=TEXTO_P0,
        created_at="2026-01-01T00:00:00",
    )

    cuerpo = _sla_http(cliente, "INC-3001")

    assert datetime.fromisoformat(cuerpo["reference_time"]) >= datetime(
        2026, 1, 1
    )
    assert cuerpo["elapsed_minutes"] > 0


def test_us3_referencia_con_zona_es_422_y_salida_2(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """FR-024: una fecha aware es entrada inválida en ambos canales."""
    cliente = TestClient(create_app())
    _alta_ok(cliente, incident_id="INC-3001", raw_text=TEXTO_P0, created_at=_iso(BASE))

    respuesta = cliente.get(
        RUTA_SLA.format(incident_id="INC-3001"),
        params={"reference_time": "2026-11-20T10:00:00+00:00"},
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "SLA_REFERENCIA_INVALIDA"

    salida = runner_cli.invoke(
        cli_app,
        [
            "sla",
            "--incident-id",
            "INC-3001",
            "--reference-time",
            "2026-11-20T10:00:00+00:00",
        ],
    )
    assert salida.exit_code == 2
    assert salida.stdout.strip() == ""
    assert "SLA_REFERENCIA_INVALIDA" in _error(salida)


def test_us3_identificador_solo_espacios_es_entrada_invalida(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """FR-017: HTTP responde 422; la consola reserva `SLA_ID_VACIO` con salida 2."""
    cliente = TestClient(create_app())

    respuesta = cliente.get("/api/v1/incidents/%20%20/sla")

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "SLA_SOLICITUD_INVALIDA"

    salida = runner_cli.invoke(cli_app, ["sla", "--incident-id", "   "])
    assert salida.exit_code == 2
    assert salida.stdout.strip() == ""
    assert "SLA_ID_VACIO" in _error(salida)


# ---------------------------------------------------------------------------
# US4 · Paridad estricta entre HTTP y consola
# ---------------------------------------------------------------------------


def _con_base(monkeypatch: pytest.MonkeyPatch, ruta: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{ruta}")


def test_us4_paridad_estricta_del_alta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, runner_cli: CliRunner
) -> None:
    """SC-004: misma entrada y mismo instante → documento estrictamente igual."""
    _con_base(monkeypatch, tmp_path / "http.db")
    por_http = _alta_ok(
        TestClient(create_app()),
        incident_id="INC-PAR",
        raw_text=TEXTO_P0,
        created_at="2026-11-20T10:00:00",
    )

    _con_base(monkeypatch, tmp_path / "cli.db")
    por_cli = _alta_cli(
        runner_cli,
        "--incident-id",
        "INC-PAR",
        "--raw-text",
        TEXTO_P0,
        "--created-at",
        "2026-11-20T10:00:00",
    )

    assert por_cli == por_http


def test_us4_paridad_estricta_del_sla(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """SC-003: mismo incidente y referencia → mismo documento en ambos canales."""
    cliente = TestClient(create_app())
    _alta_ok(cliente, incident_id="INC-PAR", raw_text=TEXTO_P0, created_at=_iso(BASE))

    por_http = _sla_http(cliente, "INC-PAR", "2026-11-20T10:45:00")
    por_cli = _sla_cli(
        runner_cli,
        "--incident-id",
        "INC-PAR",
        "--reference-time",
        "2026-11-20T10:45:00",
    )

    assert por_cli == por_http


def test_us4_fallos_equivalentes_comparten_codigo(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """FR-021: el código estable es el mismo; solo cambian estado y salida."""
    cliente = TestClient(create_app())
    _alta_ok(cliente, incident_id="INC-PAR", raw_text=TEXTO_P0, created_at=_iso(BASE))

    inexistente_http = cliente.get(RUTA_SLA.format(incident_id="INC-404"))
    inexistente_cli = runner_cli.invoke(cli_app, ["sla", "--incident-id", "INC-404"])
    assert inexistente_http.json()["code"] == "SLA_INCIDENTE_NO_ENCONTRADO"
    assert inexistente_cli.exit_code == 1
    assert "SLA_INCIDENTE_NO_ENCONTRADO" in _error(inexistente_cli)

    conflicto_http = _alta_http(
        cliente, incident_id="INC-PAR", raw_text=TEXTO_DUPLICADO
    )
    conflicto_cli = runner_cli.invoke(
        cli_app,
        ["create", "--incident-id", "INC-PAR", "--raw-text", TEXTO_DUPLICADO],
    )
    assert conflicto_http.json()["code"] == "CREATE_ID_CONFLICTO"
    assert conflicto_cli.exit_code == 1
    assert conflicto_cli.stdout.strip() == ""
    assert "CREATE_ID_CONFLICTO" in _error(conflicto_cli)

    invalido_http = cliente.get(
        RUTA_SLA.format(incident_id="INC-PAR"),
        params={"reference_time": "20/11/2026"},
    )
    invalido_cli = runner_cli.invoke(
        cli_app,
        [
            "sla",
            "--incident-id",
            "INC-PAR",
            "--reference-time",
            "20/11/2026",
        ],
    )
    assert invalido_http.json()["code"] == "SLA_REFERENCIA_INVALIDA"
    assert invalido_cli.exit_code == 2
    assert invalido_cli.stdout.strip() == ""
    assert "SLA_REFERENCIA_INVALIDA" in _error(invalido_cli)
