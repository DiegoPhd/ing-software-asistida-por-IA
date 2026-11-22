"""Pruebas de aceptación del adaptador CLI."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest
from typer.testing import CliRunner

from src.adapters.inbound.cli import app

TEXTO_P0 = (
    "URGENTE: El gateway de pagos devuelve HTTP 502 Bad Gateway en todas las "
    "transacciones con tarjeta de crédito. Ningún comercio puede cobrar."
)
TEXTO_P2 = (
    "He intentado ingresar a mi cuenta tres veces y ahora aparece bloqueada. "
    "Necesito acceder hoy mismo para enviar el informe de cierre."
)


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def _error(resultado: Any) -> str:
    return (resultado.stderr or "") + (resultado.output or "")


def test_triaje_en_linea_devuelve_json(runner: CliRunner) -> None:
    resultado = runner.invoke(
        app, ["triage", "--incident-id", "INC-1001", "--raw-text", TEXTO_P0]
    )

    assert resultado.exit_code == 0
    cuerpo: Dict[str, Any] = json.loads(resultado.stdout)
    assert cuerpo["severity"] == "P0"
    assert cuerpo["recommended_team"] == "Backend-Core"
    assert cuerpo["duplicate_group_key"] is None


def test_triaje_desde_stdin(runner: CliRunner) -> None:
    resultado = runner.invoke(
        app,
        ["triage", "--incident-id", "INC-1002", "--raw-text", "-"],
        input=TEXTO_P2,
    )

    assert resultado.exit_code == 0
    assert json.loads(resultado.stdout)["severity"] == "P2"


def test_triaje_desde_archivo(runner: CliRunner, tmp_path: Path) -> None:
    archivo = tmp_path / "reporte.json"
    archivo.write_text(
        json.dumps({"incident_id": "INC-1001", "raw_text": TEXTO_P0}, ensure_ascii=False),
        encoding="utf-8",
    )

    resultado = runner.invoke(app, ["triage", "--file", str(archivo)])

    assert resultado.exit_code == 0
    assert json.loads(resultado.stdout)["severity"] == "P0"


def test_texto_en_blanco_sale_con_codigo_2(runner: CliRunner) -> None:
    resultado = runner.invoke(
        app, ["triage", "--incident-id", "INC-1003", "--raw-text", "   "]
    )

    assert resultado.exit_code == 2
    assert resultado.stdout.strip() == ""
    assert "TRIAGE_TEXTO_VACIO" in _error(resultado)


def test_identificador_ausente_sale_con_codigo_2(runner: CliRunner) -> None:
    resultado = runner.invoke(app, ["triage", "--raw-text", TEXTO_P0])

    assert resultado.exit_code == 2
    assert "TRIAGE_ID_VACIO" in _error(resultado)


def test_fuentes_de_texto_ambiguas_salen_con_codigo_2(
    runner: CliRunner, tmp_path: Path
) -> None:
    archivo = tmp_path / "reporte.json"
    archivo.write_text(json.dumps({"raw_text": TEXTO_P0}), encoding="utf-8")

    resultado = runner.invoke(
        app, ["triage", "--raw-text", TEXTO_P0, "--file", str(archivo)]
    )

    assert resultado.exit_code == 2
    assert "TRIAGE_FUENTE_TEXTO_INVALIDA" in _error(resultado)


def test_archivo_con_lista_sale_con_codigo_2(runner: CliRunner, tmp_path: Path) -> None:
    archivo = tmp_path / "reportes.json"
    archivo.write_text(
        json.dumps([{"incident_id": "INC-1", "raw_text": TEXTO_P0}]),
        encoding="utf-8",
    )

    resultado = runner.invoke(app, ["triage", "--file", str(archivo)])

    assert resultado.exit_code == 2
    assert "TRIAGE_ARCHIVO_INVALIDO" in _error(resultado)


def test_identificador_en_conflicto_sale_con_codigo_2(
    runner: CliRunner, tmp_path: Path
) -> None:
    archivo = tmp_path / "reporte.json"
    archivo.write_text(
        json.dumps({"incident_id": "INC-2000", "raw_text": TEXTO_P0}),
        encoding="utf-8",
    )

    resultado = runner.invoke(
        app,
        ["triage", "--file", str(archivo), "--incident-id", "INC-1001"],
    )

    assert resultado.exit_code == 2
    assert "TRIAGE_ID_CONFLICTO" in _error(resultado)


def test_archivo_inexistente_sale_con_codigo_2(
    runner: CliRunner, tmp_path: Path
) -> None:
    resultado = runner.invoke(
        app, ["triage", "--file", str(tmp_path / "no-existe.json")]
    )

    assert resultado.exit_code == 2
    assert "TRIAGE_ARCHIVO_INVALIDO" in _error(resultado)
