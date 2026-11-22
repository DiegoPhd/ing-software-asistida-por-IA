"""Fixtures compartidas de la suite."""

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import app as cli_app

RAIZ = Path(__file__).resolve().parent.parent
RUTA_MUESTRA = RAIZ / "data" / "sample_incidents.json"


def cargar_reportes_de_muestra() -> List[Dict[str, Any]]:
    """Lee los diez reportes de muestra usados como evidencia."""
    return json.loads(RUTA_MUESTRA.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def reportes_muestra() -> List[Dict[str, Any]]:
    return cargar_reportes_de_muestra()


@pytest.fixture()
def cliente_http() -> TestClient:
    """Cliente HTTP contra la aplicación real, sin levantar servidor."""
    return TestClient(create_app())


@pytest.fixture()
def runner_cli() -> CliRunner:
    """Ejecutor de la aplicación Typer en proceso."""
    return CliRunner()
