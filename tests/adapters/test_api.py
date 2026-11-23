"""Pruebas de aceptación del adaptador HTTP."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.adapters.inbound.api.app import create_app
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.services import IncidentService

TEXTO_P0 = (
    "URGENTE: El gateway de pagos devuelve HTTP 502 Bad Gateway en todas las "
    "transacciones con tarjeta de crédito. Ningún comercio puede cobrar."
)
TEXTO_P2 = (
    "He intentado ingresar a mi cuenta tres veces y ahora aparece bloqueada. "
    "Necesito acceder hoy mismo para enviar el informe de cierre."
)
RUTA = "/api/v1/incidents/triage"

CAMPOS = {
    "incident_id",
    "severity",
    "component",
    "recommended_team",
    "rationale",
    "duplicate_group_key",
}


def test_caida_critica_devuelve_p0(cliente_http: TestClient) -> None:
    respuesta = cliente_http.post(
        RUTA, json={"incident_id": "INC-1001", "raw_text": TEXTO_P0}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert set(cuerpo) == CAMPOS
    assert cuerpo["incident_id"] == "INC-1001"
    assert cuerpo["severity"] == "P0"
    assert cuerpo["component"] == "payments-gateway"
    assert cuerpo["recommended_team"] == "Backend-Core"
    assert cuerpo["duplicate_group_key"] is None


def test_cuenta_bloqueada_no_es_p0(cliente_http: TestClient) -> None:
    respuesta = cliente_http.post(
        RUTA, json={"incident_id": "INC-1002", "raw_text": TEXTO_P2}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["severity"] == "P2"
    assert cuerpo["recommended_team"] == "Security-IAM"


def test_texto_en_blanco_devuelve_422(cliente_http: TestClient) -> None:
    respuesta = cliente_http.post(
        RUTA, json={"incident_id": "INC-1003", "raw_text": "   "}
    )

    assert respuesta.status_code == 422
    assert respuesta.headers["content-type"].startswith("application/problem+json")
    cuerpo = respuesta.json()
    assert cuerpo["status"] == 422
    assert cuerpo["code"] == "TRIAGE_TEXTO_VACIO"
    assert cuerpo["errors"][0]["field"] == "raw_text"


def test_identificador_vacio_devuelve_422(cliente_http: TestClient) -> None:
    respuesta = cliente_http.post(RUTA, json={"incident_id": "  ", "raw_text": TEXTO_P0})

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "TRIAGE_ID_VACIO"


def test_campo_faltante_devuelve_422_con_codigo_estable(cliente_http: TestClient) -> None:
    respuesta = cliente_http.post(RUTA, json={"incident_id": "INC-1004"})

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["code"] == "TRIAGE_SOLICITUD_INVALIDA"
    assert cuerpo["errors"][0]["field"] == "raw_text"


def test_health_responde_ok(cliente_http: TestClient) -> None:
    respuesta = cliente_http.get("/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# H003 · Contratos del alta y de la auditoría de SLA
# ---------------------------------------------------------------------------


@pytest.fixture()
def cliente_con_archivo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TestClient:
    """Cliente HTTP sobre un archivo SQLite aislado."""
    ruta = tmp_path / "api-h003.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{ruta}")
    return TestClient(create_app())


def _crear(cliente: TestClient, incident_id: str = "INC-1") -> dict:
    respuesta = cliente.post(
        "/api/v1/incidents",
        json={
            "incident_id": incident_id,
            "raw_text": TEXTO_P0,
            "created_at": "2026-11-20T10:00:00",
        },
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def test_alta_devuelve_201_con_el_documento_canonico(
    cliente_con_archivo: TestClient,
) -> None:
    """FR-012: el alta responde 201 con clasificación y aviso de duplicados."""
    respuesta = cliente_con_archivo.post(
        "/api/v1/incidents",
        json={
            "incident_id": "INC-1",
            "raw_text": TEXTO_P0,
            "created_at": "2026-11-20T10:00:00",
        },
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["status"] == "OPEN"
    assert cuerpo["is_duplicate"] is False
    assert cuerpo["duplicate_of"] == []


def test_la_auditoria_devuelve_200_con_el_documento_canonico(
    cliente_con_archivo: TestClient,
) -> None:
    """FR-018: la auditoría responde 200 y no entrega un documento de alta."""
    _crear(cliente_con_archivo)

    respuesta = cliente_con_archivo.get(
        "/api/v1/incidents/INC-1/sla",
        params={"reference_time": "2026-11-20T10:45:00"},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["elapsed_minutes"] == 45
    assert cuerpo["window"] == "24x7"
    assert "duplicate_of" not in cuerpo


def test_rutas_ajenas_al_contrato_responden_problem_json(
    cliente_con_archivo: TestClient,
) -> None:
    """T033: un método o una ruta fuera del contrato no devuelve datos parciales."""
    metodo = cliente_con_archivo.delete("/api/v1/incidents")
    ruta = cliente_con_archivo.get("/api/v1/incidents/no-existe/otra")

    assert metodo.status_code == 405
    assert metodo.headers["content-type"].startswith("application/problem+json")
    assert ruta.status_code == 404
    assert ruta.headers["content-type"].startswith("application/problem+json")


def test_campo_desconocido_en_el_cuerpo_es_422(cliente_con_archivo: TestClient) -> None:
    """FR-029: los campos fuera del contrato no se ignoran en silencio."""
    respuesta = cliente_con_archivo.post(
        "/api/v1/incidents",
        json={
            "incident_id": "INC-1",
            "raw_text": TEXTO_P0,
            "severity": "P0",
        },
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "CREATE_SOLICITUD_INVALIDA"


def test_created_at_con_tipo_incorrecto_es_create_creacion_invalida(
    cliente_con_archivo: TestClient,
) -> None:
    """FR-024: un `created_at` no textual es fecha inválida, no esquema genérico."""
    respuesta = cliente_con_archivo.post(
        "/api/v1/incidents",
        json={"incident_id": "INC-1", "raw_text": TEXTO_P0, "created_at": 123},
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "CREATE_CREACION_INVALIDA"


def test_parametro_desconocido_en_el_alta_es_422(
    cliente_con_archivo: TestClient,
) -> None:
    """FR-029: el alta no admite parámetros de consulta."""
    respuesta = cliente_con_archivo.post(
        "/api/v1/incidents?foo=1",
        json={"incident_id": "INC-1", "raw_text": TEXTO_P0},
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "CREATE_SOLICITUD_INVALIDA"
    assert "is_duplicate" not in respuesta.json()


@pytest.mark.parametrize(
    "parametros",
    [{"desconocido": "1"}, [("reference_time", "a"), ("reference_time", "b")]],
)
def test_parametros_invalidos_en_la_auditoria_son_422(
    cliente_con_archivo: TestClient, parametros: object
) -> None:
    """FR-029: el SLA rechaza parámetros desconocidos o repetidos."""
    _crear(cliente_con_archivo)

    respuesta = cliente_con_archivo.get(
        "/api/v1/incidents/INC-1/sla", params=parametros
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "SLA_SOLICITUD_INVALIDA"
    assert "elapsed_minutes" not in respuesta.json()


def test_identificador_solo_espacios_en_la_auditoria_es_422(
    cliente_con_archivo: TestClient,
) -> None:
    """FR-017: un identificador en blanco no alcanza una consulta válida."""
    respuesta = cliente_con_archivo.get("/api/v1/incidents/%20%20/sla")

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "SLA_SOLICITUD_INVALIDA"


def test_datos_incoherentes_responden_409_sla_datos_inconsistentes() -> None:
    """FR-031: un terminal sin resolución es 409 sin valores por defecto."""
    repositorio = SQLiteIncidentRepository()
    repositorio.conn.execute(
        "INSERT INTO incidents (incident_id, title, component, severity, status, "
        "created_at, resolved_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "INC-ROTO",
            "Terminal sin resolución",
            "payments-gateway",
            "P0",
            "RESOLVED",
            "2026-11-20T10:00:00",
            None,
        ),
    )
    repositorio.conn.commit()
    cliente = TestClient(create_app(IncidentService(repositorio)))

    respuesta = cliente.get(
        "/api/v1/incidents/INC-ROTO/sla",
        params={"reference_time": "2026-11-20T11:00:00"},
    )

    assert respuesta.status_code == 409
    assert respuesta.headers["content-type"].startswith("application/problem+json")
    assert respuesta.json()["code"] == "SLA_DATOS_INCONSISTENTES"
    assert "elapsed_minutes" not in respuesta.json()


def test_el_conflicto_de_alta_es_409_create_id_conflicto(
    cliente_con_archivo: TestClient,
) -> None:
    """FR-008: repetir el identificador no sobrescribe el previo."""
    _crear(cliente_con_archivo)

    respuesta = cliente_con_archivo.post(
        "/api/v1/incidents",
        json={"incident_id": "INC-1", "raw_text": TEXTO_P2},
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "CREATE_ID_CONFLICTO"
