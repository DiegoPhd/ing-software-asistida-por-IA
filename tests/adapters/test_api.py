"""Pruebas de aceptación del adaptador HTTP."""

from fastapi.testclient import TestClient

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
