"""Pruebas de aceptación BDD de H002: resumen de incidentes activos.

Cada escenario sigue Dado / Cuando / Entonces (Constitución §3.2). La paridad
HTTP/CLI se verifica comparando documentos JSON por igualdad estricta.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import app as cli_app
from src.adapters.inbound.summary_contract import to_summary_response
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.domain.models import Incident
from src.domain.sla_calculator import summarize_active_incidents

RUTA = "/api/v1/incidents/summary"
REFERENCIA = datetime(2026, 11, 20, 12, 0, 0)  # viernes
REFERENCIA_TEXTO = "2026-11-20T12:00:00"
TITULO_ESPECIAL = 'Pasarela «caída»: "pagos" & más — 100 %'


def _inc(
    incident_id: str,
    component: str = "payments-gateway",
    severity: str = "P0",
    status: str = "OPEN",
    created_at: datetime = REFERENCIA,
    resolved_at: Optional[datetime] = None,
    title: Optional[str] = None,
) -> Incident:
    return Incident(
        incident_id=incident_id,
        title=title or f"Incidente {incident_id}",
        component=component,
        severity=severity,
        status=status,
        created_at=created_at,
        resolved_at=resolved_at,
    )


def _sembrar(ruta: Path, incidentes: List[Incident]) -> None:
    repositorio = SQLiteIncidentRepository(str(ruta))
    for incidente in incidentes:
        repositorio.save_incident(incidente)


def _incidentes_us1() -> List[Incident]:
    """5 activos y 3 terminales; solo INC-2001 incumple (61 min de 60)."""
    return [
        _inc("INC-2001", "payments-gateway", "P0", "OPEN", datetime(2026, 11, 20, 10, 59)),
        _inc("INC-2002", "reporting-api", "P2", "IN_PROGRESS", datetime(2026, 11, 19, 16, 0)),
        _inc("INC-2003", "auth-identity", "P1", "OPEN", datetime(2026, 11, 20, 10, 0)),
        _inc("INC-2004", "database-cluster", "P3", "OPEN", datetime(2026, 11, 20, 9, 0)),
        _inc("INC-2005", "frontend-ui", "P0", "IN_PROGRESS", datetime(2026, 11, 20, 11, 30)),
        _inc(
            "INC-2006",
            "payments-gateway",
            "P0",
            "RESOLVED",
            datetime(2026, 11, 19, 9, 0),
            datetime(2026, 11, 19, 10, 30),
        ),
        _inc(
            "INC-2007",
            "reporting-api",
            "P2",
            "CLOSED",
            datetime(2026, 11, 18, 9, 0),
            datetime(2026, 11, 19, 9, 0),
        ),
        _inc(
            "INC-2008",
            "auth-identity",
            "P1",
            "RESOLVED",
            datetime(2026, 11, 19, 8, 0),
            datetime(2026, 11, 19, 8, 30),
        ),
    ]


def _incidentes_frontera() -> List[Incident]:
    """P0 en 44/45/46 y P2 en 479/480/481 minutos contra el mismo instante."""
    lunes = datetime(2026, 11, 16, 8, 0, 0)
    referencia = lunes + timedelta(minutes=481)
    return [
        _inc("INC-P0-44", severity="P0", created_at=referencia - timedelta(minutes=44)),
        _inc("INC-P0-45", severity="P0", created_at=referencia - timedelta(minutes=45)),
        _inc("INC-P0-46", severity="P0", created_at=referencia - timedelta(minutes=46)),
        _inc("INC-P2-479", severity="P2", created_at=referencia - timedelta(minutes=479)),
        _inc("INC-P2-480", severity="P2", created_at=referencia - timedelta(minutes=480)),
        _inc("INC-P2-481", severity="P2", created_at=referencia - timedelta(minutes=481)),
    ]


@pytest.fixture()
def base_temporal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Archivo SQLite aislado con `DATABASE_URL` apuntando a él."""
    ruta = tmp_path / "resumen.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{ruta}")
    return ruta


def _error(resultado: Any) -> str:
    return (resultado.stderr or "") + (resultado.output or "")


def _resumen_http(
    cliente: TestClient, parametros: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    respuesta = cliente.get(RUTA, params=parametros or {})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


def _resumen_cli(runner: CliRunner, argumentos: List[str]) -> Dict[str, Any]:
    salida = runner.invoke(cli_app, ["summary", *argumentos])
    assert salida.exit_code == 0, _error(salida)
    return json.loads(salida.stdout)


# ---------------------------------------------------------------------------
# US1 · Consultar el resumen por HTTP
# ---------------------------------------------------------------------------


def test_us1_resumen_global_excluye_terminales(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """Dado 5 activos y 3 terminales, Cuando consulto, Entonces solo hay 5."""
    _sembrar(base_temporal, _incidentes_us1())
    cliente = TestClient(create_app())

    cuerpo = _resumen_http(cliente, {"reference_time": REFERENCIA_TEXTO})

    assert cuerpo["total_active"] == 5
    assert cuerpo["breached_count"] == 1
    identificadores = [item["incident_id"] for item in cuerpo["incidents"]]
    assert identificadores == [
        "INC-2001",
        "INC-2005",
        "INC-2003",
        "INC-2002",
        "INC-2004",
    ]
    assert {"INC-2006", "INC-2007", "INC-2008"}.isdisjoint(identificadores)
    assert {item["status"] for item in cuerpo["incidents"]} == {"OPEN", "IN_PROGRESS"}


def test_us1_total_incumplido_coincide_con_el_detalle(base_temporal: Path) -> None:
    """Dado 4 activos con 2 incumplidos, Entonces el total es 2 y el detalle lo refleja."""
    _sembrar(
        base_temporal,
        [
            _inc("INC-1", created_at=REFERENCIA - timedelta(minutes=61)),
            _inc("INC-2", created_at=REFERENCIA - timedelta(minutes=60)),
            _inc("INC-3", created_at=REFERENCIA - timedelta(minutes=120)),
            _inc("INC-4", created_at=REFERENCIA - timedelta(minutes=30)),
        ],
    )
    cliente = TestClient(create_app())

    cuerpo = _resumen_http(cliente, {"reference_time": REFERENCIA_TEXTO})

    assert cuerpo["total_active"] == 4
    assert cuerpo["breached_count"] == 2
    assert sum(1 for item in cuerpo["incidents"] if item["is_breached"]) == 2
    assert {item["incident_id"] for item in cuerpo["incidents"] if item["is_breached"]} == {
        "INC-1",
        "INC-3",
    }


def test_us1_detalle_completo_por_incidente(base_temporal: Path) -> None:
    """Cada entrada presenta título, componente, severidad, estado y SLA."""
    _sembrar(base_temporal, _incidentes_us1())
    cliente = TestClient(create_app())

    cuerpo = _resumen_http(cliente, {"reference_time": REFERENCIA_TEXTO})
    detalle = next(
        item for item in cuerpo["incidents"] if item["incident_id"] == "INC-2002"
    )

    assert detalle == {
        "incident_id": "INC-2002",
        "title": "Incidente INC-2002",
        "component": "reporting-api",
        "severity": "P2",
        "status": "IN_PROGRESS",
        "elapsed_minutes": 360,
        "is_breached": False,
        "requires_escalation": True,
    }


def test_us1_resumen_vacio_termina_con_exito(base_temporal: Path) -> None:
    """Dado que no hay activos, Entonces 200 con totales en cero."""
    cliente = TestClient(create_app())

    respuesta = cliente.get(RUTA, params={"reference_time": REFERENCIA_TEXTO})

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "total_active": 0,
        "breached_count": 0,
        "incidents": [],
    }


def test_us1_titulo_con_acentos_y_comillas_no_se_altera(base_temporal: Path) -> None:
    """Los títulos conservan el texto original, sin truncar ni sustituir."""
    _sembrar(base_temporal, [_inc("INC-ESP", title=TITULO_ESPECIAL)])
    cliente = TestClient(create_app())

    cuerpo = _resumen_http(cliente, {"reference_time": REFERENCIA_TEXTO})

    assert cuerpo["incidents"][0]["title"] == TITULO_ESPECIAL


def test_us1_sin_reference_time_sobre_base_vacia(base_temporal: Path) -> None:
    """FR-020: omitir el instante usa el actual; una base vacía da ceros."""
    cliente = TestClient(create_app())

    cuerpo = _resumen_http(cliente)

    assert cuerpo == {"total_active": 0, "breached_count": 0, "incidents": []}


@pytest.mark.parametrize(
    "referencia",
    ["2026-11-20T12:00:00+00:00", "2026-11-20 12:00:00", "2026-13-40T12:00:00"],
)
def test_us1_reference_time_invalido_devuelve_422(
    base_temporal: Path, referencia: str
) -> None:
    """Fecha con zona, con espacio o imposible → 422 sin cuerpo de resumen."""
    cliente = TestClient(create_app())

    respuesta = cliente.get(RUTA, params={"reference_time": referencia})

    assert respuesta.status_code == 422
    assert respuesta.headers["content-type"].startswith("application/problem+json")
    cuerpo = respuesta.json()
    assert cuerpo["code"] == "SUMMARY_REFERENCIA_INVALIDA"
    assert "total_active" not in cuerpo


@pytest.mark.parametrize("parametro", [{"desconocido": "1"}, {"component": "a", "x": "b"}])
def test_us1_parametro_desconocido_devuelve_422(
    base_temporal: Path, parametro: Dict[str, str]
) -> None:
    """Un parámetro fuera del contrato es 422 SUMMARY_SOLICITUD_INVALIDA."""
    cliente = TestClient(create_app())

    respuesta = cliente.get(RUTA, params=parametro)

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "SUMMARY_SOLICITUD_INVALIDA"
    assert "incidents" not in respuesta.json()


def test_us1_incoherencia_temporal_devuelve_409_sin_totales(
    base_temporal: Path,
) -> None:
    """Un activo creado después del instante rechaza el resumen completo."""
    _sembrar(
        base_temporal,
        [_inc("INC-FUTURO", created_at=REFERENCIA + timedelta(minutes=1))],
    )
    cliente = TestClient(create_app())

    respuesta = cliente.get(RUTA, params={"reference_time": REFERENCIA_TEXTO})

    assert respuesta.status_code == 409
    cuerpo = respuesta.json()
    assert cuerpo["code"] == "SUMMARY_REFERENCIA_INCONSISTENTE"
    assert "total_active" not in cuerpo
    assert "incidents" not in cuerpo


def test_us1_terminal_con_sla_vencido_no_aparece(base_temporal: Path) -> None:
    """Un RESOLVED de 90 minutos P0 quedaría incumplido, pero está fuera."""
    _sembrar(
        base_temporal,
        [
            _inc(
                "INC-RESUELTO",
                status="RESOLVED",
                created_at=REFERENCIA - timedelta(hours=2),
                resolved_at=REFERENCIA - timedelta(minutes=30),
            )
        ],
    )
    cliente = TestClient(create_app())

    cuerpo = _resumen_http(cliente, {"reference_time": REFERENCIA_TEXTO})

    assert cuerpo["total_active"] == 0
    assert cuerpo["incidents"] == []


# ---------------------------------------------------------------------------
# US2 · El mismo resumen por consola
# ---------------------------------------------------------------------------


def test_us2_paridad_http_y_cli(base_temporal: Path, runner_cli: CliRunner) -> None:
    """SC-003: mismos datos e instante → documento estrictamente igual."""
    _sembrar(base_temporal, _incidentes_us1())
    cliente = TestClient(create_app())

    por_http = _resumen_http(cliente, {"reference_time": REFERENCIA_TEXTO})
    por_cli = _resumen_cli(runner_cli, ["--reference-time", REFERENCIA_TEXTO])

    assert por_cli == por_http


def test_us2_paridad_en_resultado_vacio(base_temporal: Path, runner_cli: CliRunner) -> None:
    """El resultado vacío sale con código 0 y el mismo documento."""
    cliente = TestClient(create_app())

    por_http = _resumen_http(cliente, {"reference_time": REFERENCIA_TEXTO})
    salida = runner_cli.invoke(
        cli_app, ["summary", "--reference-time", REFERENCIA_TEXTO]
    )

    assert salida.exit_code == 0
    assert json.loads(salida.stdout) == por_http


def test_us2_titulo_especial_identico_en_ambos_canales(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """Acentos, comillas y caracteres especiales sobreviven a los dos canales."""
    _sembrar(base_temporal, [_inc("INC-ESP", title=TITULO_ESPECIAL)])
    cliente = TestClient(create_app())

    por_http = _resumen_http(cliente, {"reference_time": REFERENCIA_TEXTO})
    por_cli = _resumen_cli(runner_cli, ["--reference-time", REFERENCIA_TEXTO])

    assert por_http["incidents"][0]["title"] == TITULO_ESPECIAL
    assert por_cli == por_http


def test_us2_fronteras_de_sla_coinciden_en_los_tres_caminos(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """SC-005: fronteras idénticas en dominio, HTTP y CLI."""
    _sembrar(base_temporal, _incidentes_frontera())
    referencia = datetime(2026, 11, 16, 16, 1, 0)
    referencia_texto = "2026-11-16T16:01:00"
    cliente = TestClient(create_app())

    por_http = _resumen_http(cliente, {"reference_time": referencia_texto})
    por_cli = _resumen_cli(runner_cli, ["--reference-time", referencia_texto])

    repositorio = SQLiteIncidentRepository(str(base_temporal))
    resumen_dominio = summarize_active_incidents(
        repositorio.list_active_incidents(None), referencia
    )
    por_dominio = to_summary_response(resumen_dominio).model_dump()

    assert por_http == por_cli == por_dominio

    banderas = {
        item["incident_id"]: (item["is_breached"], item["requires_escalation"])
        for item in por_http["incidents"]
    }
    assert banderas["INC-P0-44"] == (False, False)
    assert banderas["INC-P0-45"] == (False, True)
    assert banderas["INC-P0-46"] == (False, True)
    assert banderas["INC-P2-479"] == (False, True)
    assert banderas["INC-P2-480"] == (False, True)
    assert banderas["INC-P2-481"] == (True, False)


@pytest.mark.parametrize(
    "referencia", ["2026-11-20T12:00:00+00:00", "2026-11-20 12:00:00", "no-es-fecha"]
)
def test_us2_fecha_invalida_sale_con_codigo_2(
    base_temporal: Path, runner_cli: CliRunner, referencia: str
) -> None:
    """La CLI traduce la fecha inválida a código 2 y stderr problem+json."""
    salida = runner_cli.invoke(cli_app, ["summary", "--reference-time", referencia])

    assert salida.exit_code == 2
    assert salida.stdout.strip() == ""
    assert "SUMMARY_REFERENCIA_INVALIDA" in _error(salida)


def test_us2_incoherencia_temporal_sale_con_codigo_1(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """Un dato incoherente es código 1, sin resumen parcial en stdout."""
    _sembrar(
        base_temporal,
        [_inc("INC-FUTURO", created_at=REFERENCIA + timedelta(minutes=1))],
    )

    salida = runner_cli.invoke(
        cli_app, ["summary", "--reference-time", REFERENCIA_TEXTO]
    )

    assert salida.exit_code == 1
    assert salida.stdout.strip() == ""
    assert "SUMMARY_REFERENCIA_INCONSISTENTE" in _error(salida)


# ---------------------------------------------------------------------------
# US3 · Filtrar el resumen por componente
# ---------------------------------------------------------------------------


def _incidentes_por_componente() -> List[Incident]:
    return [
        _inc("INC-A1", "payments-gateway", "P0", created_at=REFERENCIA - timedelta(minutes=61)),
        _inc("INC-A2", "payments-gateway", "P1", created_at=REFERENCIA - timedelta(minutes=10)),
        _inc("INC-B1", "auth-identity", "P2", created_at=REFERENCIA - timedelta(minutes=60)),
        _inc("INC-B2", "auth-identity", "P0", created_at=REFERENCIA - timedelta(minutes=5)),
    ]


def test_us3_filtro_por_componente_en_ambos_canales(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """El filtro reduce detalle y totales al subconjunto del componente."""
    _sembrar(base_temporal, _incidentes_por_componente())
    cliente = TestClient(create_app())

    por_http = _resumen_http(
        cliente, {"component": "payments-gateway", "reference_time": REFERENCIA_TEXTO}
    )
    por_cli = _resumen_cli(
        runner_cli,
        ["--component", "payments-gateway", "--reference-time", REFERENCIA_TEXTO],
    )

    assert por_http["total_active"] == 2
    assert por_http["breached_count"] == 1
    assert {item["component"] for item in por_http["incidents"]} == {"payments-gateway"}
    assert por_cli == por_http


def test_us3_componente_sin_coincidencias_es_exito(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """SC-007: un componente inexistente no es un error."""
    _sembrar(base_temporal, _incidentes_por_componente())
    cliente = TestClient(create_app())

    por_http = _resumen_http(
        cliente, {"component": "no-existe", "reference_time": REFERENCIA_TEXTO}
    )
    por_cli = _resumen_cli(
        runner_cli,
        ["--component", "no-existe", "--reference-time", REFERENCIA_TEXTO],
    )

    assert por_http == {"total_active": 0, "breached_count": 0, "incidents": []}
    assert por_cli == por_http


def test_us3_espacios_sobrantes_se_ignoran(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """FR-010: el filtro se compara tras recortar espacios exteriores."""
    _sembrar(base_temporal, _incidentes_por_componente())
    cliente = TestClient(create_app())

    con_espacios = _resumen_http(
        cliente,
        {"component": "  payments-gateway  ", "reference_time": REFERENCIA_TEXTO},
    )
    sin_espacios = _resumen_http(
        cliente, {"component": "payments-gateway", "reference_time": REFERENCIA_TEXTO}
    )
    por_cli = _resumen_cli(
        runner_cli,
        ["--component", "  payments-gateway  ", "--reference-time", REFERENCIA_TEXTO],
    )

    assert con_espacios == sin_espacios
    assert por_cli == sin_espacios


@pytest.mark.parametrize("parametros", [{}, {"component": ""}, {"component": "   "}])
def test_us3_filtro_ausente_o_vacio_equivale_a_todos(
    base_temporal: Path, parametros: Dict[str, str]
) -> None:
    """FR-010: ausente, vacío o solo espacios incluye todos los activos."""
    _sembrar(base_temporal, _incidentes_por_componente())
    cliente = TestClient(create_app())

    cuerpo = _resumen_http(
        cliente, {**parametros, "reference_time": REFERENCIA_TEXTO}
    )

    assert cuerpo["total_active"] == 4
    assert {item["component"] for item in cuerpo["incidents"]} == {
        "payments-gateway",
        "auth-identity",
    }


def test_us3_componente_demasiado_largo_http(base_temporal: Path) -> None:
    """FR-016: más de 128 caracteres es 422 con código estable."""
    cliente = TestClient(create_app())

    respuesta = cliente.get(
        RUTA,
        params={"component": "c" * 129, "reference_time": REFERENCIA_TEXTO},
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "SUMMARY_COMPONENTE_DEMASIADO_LARGO"
    assert "total_active" not in respuesta.json()


def test_us3_componente_demasiado_largo_cli(
    base_temporal: Path, runner_cli: CliRunner
) -> None:
    """La CLI traduce el componente largo a código 2 sin resumen parcial."""
    salida = runner_cli.invoke(
        cli_app,
        ["summary", "--component", "c" * 129, "--reference-time", REFERENCIA_TEXTO],
    )

    assert salida.exit_code == 2
    assert salida.stdout.strip() == ""
    assert "SUMMARY_COMPONENTE_DEMASIADO_LARGO" in _error(salida)
