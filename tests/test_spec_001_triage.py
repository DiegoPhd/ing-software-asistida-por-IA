"""Pruebas de aceptación BDD de la especificación 001 (H001).

Cada escenario sigue el formato Dado / Cuando / Entonces de la Constitución §3.2.
"""

import json
from typing import Any, Dict, List

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.cli import app

RUTA = "/api/v1/incidents/triage"

TEXTO_P0 = (
    "URGENTE: El gateway de pagos devuelve HTTP 502 Bad Gateway en todas las "
    "transacciones con tarjeta de crédito. Ningún comercio puede cobrar."
)
TEXTO_P2 = (
    "He intentado ingresar a mi cuenta tres veces y ahora aparece bloqueada. "
    "Necesito acceder hoy mismo para enviar el informe de cierre."
)


def test_e01_caida_critica_http_502_en_la_pasarela_de_pagos(cliente_http: TestClient) -> None:
    """E-01: una caída de pagos se clasifica como P0 y se enruta a Backend-Core."""
    # Dado un reporte con indisponibilidad real en la pasarela de pagos
    cuerpo = {"incident_id": "INC-1001", "raw_text": TEXTO_P0}

    # Cuando se envía el reporte al endpoint de triaje
    respuesta = cliente_http.post(RUTA, json=cuerpo)

    # Entonces responde 200 con severidad P0, componente y equipo esperados
    assert respuesta.status_code == 200
    resultado = respuesta.json()
    assert resultado["severity"] == "P0"
    assert resultado["component"] == "payments-gateway"
    assert resultado["recommended_team"] == "Backend-Core"
    assert resultado["duplicate_group_key"] is None


def test_e02_cuenta_bloqueada_que_menciona_hoy_no_es_p0(cliente_http: TestClient) -> None:
    """E-02: "hoy" no es un criterio de impacto y no dispara un falso P0."""
    # Dado un reporte de cuenta individual bloqueada que menciona "hoy"
    cuerpo = {"incident_id": "INC-1002", "raw_text": TEXTO_P2}

    # Cuando se envía el reporte al endpoint de triaje
    respuesta = cliente_http.post(RUTA, json=cuerpo)

    # Entonces la severidad es P2 y el equipo es Security-IAM
    assert respuesta.status_code == 200
    resultado = respuesta.json()
    assert resultado["severity"] == "P2"
    assert resultado["component"] == "auth-identity"
    assert resultado["recommended_team"] == "Security-IAM"


def test_e03_entradas_vacias_o_con_solo_espacios_devuelven_422(
    cliente_http: TestClient,
) -> None:
    """E-03: los campos vacíos se rechazan con un código estable."""
    # Dado un reporte con raw_text de solo espacios
    # Cuando se envía al endpoint de triaje
    respuesta_texto = cliente_http.post(
        RUTA, json={"incident_id": "INC-1003", "raw_text": "   "}
    )

    # Entonces responde 422 con problem+json y el código de texto vacío
    assert respuesta_texto.status_code == 422
    assert respuesta_texto.headers["content-type"].startswith("application/problem+json")
    assert respuesta_texto.json()["code"] == "TRIAGE_TEXTO_VACIO"

    # Dado un reporte con incident_id vacío
    # Cuando se envía al endpoint de triaje
    respuesta_id = cliente_http.post(RUTA, json={"incident_id": "", "raw_text": TEXTO_P0})

    # Entonces responde 422 con el código de identificador vacío
    assert respuesta_id.status_code == 422
    assert respuesta_id.json()["code"] == "TRIAGE_ID_VACIO"


def test_e04_paridad_de_la_cli_con_el_caso_critico(runner_cli: CliRunner) -> None:
    """E-04: la CLI produce el mismo JSON que HTTP para el reporte crítico."""
    # Dado el reporte crítico pasado por terminal
    # Cuando se ejecuta el subcomando triage
    salida = runner_cli.invoke(
        app, ["triage", "--incident-id", "INC-1001", "--raw-text", TEXTO_P0]
    )

    # Entonces termina con código 0 y devuelve P0 con Backend-Core
    assert salida.exit_code == 0
    resultado: Dict[str, Any] = json.loads(salida.stdout)
    assert resultado["severity"] == "P0"
    assert resultado["recommended_team"] == "Backend-Core"


def test_paridad_http_y_cli_sobre_los_reportes_de_muestra(
    cliente_http: TestClient,
    runner_cli: CliRunner,
    reportes_muestra: List[Dict[str, Any]],
) -> None:
    """Criterio de cierre de H001: misma clasificación en ambas interfaces."""
    for reporte in reportes_muestra:
        respuesta = cliente_http.post(
            RUTA,
            json={"incident_id": reporte["id"], "raw_text": reporte["raw_text"]},
        )
        salida = runner_cli.invoke(
            app,
            [
                "triage",
                "--incident-id",
                reporte["id"],
                "--raw-text",
                reporte["raw_text"],
            ],
        )

        assert respuesta.status_code == 200, reporte["id"]
        assert salida.exit_code == 0, (reporte["id"], salida.stderr)
        assert json.loads(salida.stdout) == respuesta.json(), reporte["id"]
