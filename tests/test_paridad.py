"""Paridad entre las dos interfaces de entrada.

Criterio de cierre de H001: un mismo reporte produce la misma clasificación y el
mismo enrutamiento en web y terminal.
"""

import json
from typing import Any, Dict, List

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.cli import app as app_cli
from src.adapters.inbound.api.app import create_app

RUTA = "/api/v1/incidents/triage"


def test_http_y_cli_producen_el_mismo_json(reportes_muestra: List[Dict[str, Any]]) -> None:
    cliente = TestClient(create_app())
    runner = CliRunner()

    for reporte in reportes_muestra:
        respuesta = cliente.post(
            RUTA,
            json={"incident_id": reporte["id"], "raw_text": reporte["raw_text"]},
        )
        salida = runner.invoke(
            app_cli,
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
