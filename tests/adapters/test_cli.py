"""Pruebas de aceptación del adaptador CLI."""

import json
from pathlib import Path
from typing import Any, Dict

import pytest
from typer.testing import CliRunner

from src.adapters.inbound.cli import app
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository

TEXTO_P0 = (
    "URGENTE: El gateway de pagos devuelve HTTP 502 Bad Gateway en todas las "
    "transacciones con tarjeta de crédito. Ningún comercio puede cobrar."
)
TEXTO_P2 = (
    "He intentado ingresar a mi cuenta tres veces y ahora aparece bloqueada. "
    "Necesito acceder hoy mismo para enviar el informe de cierre."
)


def _error(resultado: Any) -> str:
    return (resultado.stderr or "") + (resultado.output or "")


def test_triaje_en_linea_devuelve_json(runner_cli: CliRunner) -> None:
    resultado = runner_cli.invoke(
        app, ["triage", "--incident-id", "INC-1001", "--raw-text", TEXTO_P0]
    )

    assert resultado.exit_code == 0
    cuerpo: Dict[str, Any] = json.loads(resultado.stdout)
    assert cuerpo["severity"] == "P0"
    assert cuerpo["recommended_team"] == "Backend-Core"
    assert cuerpo["duplicate_group_key"] is None


def test_triaje_desde_stdin(runner_cli: CliRunner) -> None:
    resultado = runner_cli.invoke(
        app,
        ["triage", "--incident-id", "INC-1002", "--raw-text", "-"],
        input=TEXTO_P2,
    )

    assert resultado.exit_code == 0
    assert json.loads(resultado.stdout)["severity"] == "P2"


def test_triaje_desde_archivo(runner_cli: CliRunner, tmp_path: Path) -> None:
    archivo = tmp_path / "reporte.json"
    archivo.write_text(
        json.dumps({"incident_id": "INC-1001", "raw_text": TEXTO_P0}, ensure_ascii=False),
        encoding="utf-8",
    )

    resultado = runner_cli.invoke(app, ["triage", "--file", str(archivo)])

    assert resultado.exit_code == 0
    assert json.loads(resultado.stdout)["severity"] == "P0"


def test_texto_en_blanco_sale_con_codigo_2(runner_cli: CliRunner) -> None:
    resultado = runner_cli.invoke(
        app, ["triage", "--incident-id", "INC-1003", "--raw-text", "   "]
    )

    assert resultado.exit_code == 2
    assert resultado.stdout.strip() == ""
    assert "TRIAGE_TEXTO_VACIO" in _error(resultado)


def test_identificador_ausente_sale_con_codigo_2(runner_cli: CliRunner) -> None:
    resultado = runner_cli.invoke(app, ["triage", "--raw-text", TEXTO_P0])

    assert resultado.exit_code == 2
    assert "TRIAGE_ID_VACIO" in _error(resultado)


def test_fuentes_de_texto_ambiguas_salen_con_codigo_2(
    runner_cli: CliRunner, tmp_path: Path
) -> None:
    archivo = tmp_path / "reporte.json"
    archivo.write_text(json.dumps({"raw_text": TEXTO_P0}), encoding="utf-8")

    resultado = runner_cli.invoke(
        app, ["triage", "--raw-text", TEXTO_P0, "--file", str(archivo)]
    )

    assert resultado.exit_code == 2
    assert "TRIAGE_FUENTE_TEXTO_INVALIDA" in _error(resultado)


def test_archivo_con_lista_sale_con_codigo_2(runner_cli: CliRunner, tmp_path: Path) -> None:
    archivo = tmp_path / "reportes.json"
    archivo.write_text(
        json.dumps([{"incident_id": "INC-1", "raw_text": TEXTO_P0}]),
        encoding="utf-8",
    )

    resultado = runner_cli.invoke(app, ["triage", "--file", str(archivo)])

    assert resultado.exit_code == 2
    assert "TRIAGE_ARCHIVO_INVALIDO" in _error(resultado)


def test_identificador_en_conflicto_sale_con_codigo_2(
    runner_cli: CliRunner, tmp_path: Path
) -> None:
    archivo = tmp_path / "reporte.json"
    archivo.write_text(
        json.dumps({"incident_id": "INC-2000", "raw_text": TEXTO_P0}),
        encoding="utf-8",
    )

    resultado = runner_cli.invoke(
        app,
        ["triage", "--file", str(archivo), "--incident-id", "INC-1001"],
    )

    assert resultado.exit_code == 2
    assert "TRIAGE_ID_CONFLICTO" in _error(resultado)


def test_archivo_inexistente_sale_con_codigo_2(
    runner_cli: CliRunner, tmp_path: Path
) -> None:
    resultado = runner_cli.invoke(
        app, ["triage", "--file", str(tmp_path / "no-existe.json")]
    )

    assert resultado.exit_code == 2
    assert "TRIAGE_ARCHIVO_INVALIDO" in _error(resultado)


# ---------------------------------------------------------------------------
# H003 · Subcomandos `create` y `sla`
# ---------------------------------------------------------------------------


@pytest.fixture()
def base_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Archivo SQLite aislado compartido entre invocaciones del comando."""
    ruta = tmp_path / "cli-h003.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{ruta}")
    return ruta


def _crear(runner_cli: CliRunner, incident_id: str = "INC-1") -> Dict[str, Any]:
    salida = runner_cli.invoke(
        app,
        [
            "create",
            "--incident-id",
            incident_id,
            "--raw-text",
            TEXTO_P0,
            "--created-at",
            "2026-11-20T10:00:00",
        ],
    )
    assert salida.exit_code == 0, _error(salida)
    return json.loads(salida.stdout)


def test_create_sale_con_cero_y_documento_json(
    base_cli: Path, runner_cli: CliRunner
) -> None:
    """FR-012/FR-021: éxito con JSON y los campos del contrato."""
    cuerpo = _crear(runner_cli)

    assert cuerpo["incident_id"] == "INC-1"
    assert cuerpo["status"] == "OPEN"
    assert cuerpo["created_at"] == "2026-11-20T10:00:00"
    assert cuerpo["is_duplicate"] is False
    assert cuerpo["duplicate_of"] == []


@pytest.mark.parametrize(
    "created_at", ["2026-11-20 10:00:00", "2026-11-20T10:00:00+00:00"]
)
def test_create_con_fecha_invalida_sale_con_2(
    base_cli: Path, runner_cli: CliRunner, created_at: str
) -> None:
    """FR-024: fecha con espacio o con zona es entrada inválida."""
    salida = runner_cli.invoke(
        app,
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
    assert SQLiteIncidentRepository(str(base_cli)).get_incident("INC-1") is None


def test_create_con_identificador_repetido_sale_con_1(
    base_cli: Path, runner_cli: CliRunner
) -> None:
    """FR-008: el conflicto no sobrescribe ni imprime un documento parcial."""
    original = _crear(runner_cli)

    salida = runner_cli.invoke(
        app,
        [
            "create",
            "--incident-id",
            "INC-1",
            "--raw-text",
            "Otro texto completamente distinto.",
            "--created-at",
            "2026-11-20T11:00:00",
        ],
    )

    assert salida.exit_code == 1
    assert salida.stdout.strip() == ""
    assert "CREATE_ID_CONFLICTO" in _error(salida)
    persistido = SQLiteIncidentRepository(str(base_cli)).get_incident("INC-1")
    assert persistido is not None
    assert persistido.raw_text == TEXTO_P0
    assert persistido.created_at.isoformat() == original["created_at"]


def test_sla_sale_con_cero_y_documento_json(
    base_cli: Path, runner_cli: CliRunner
) -> None:
    """FR-018: la auditoría por consola informa contexto y ventana."""
    _crear(runner_cli)

    salida = runner_cli.invoke(
        app,
        [
            "sla",
            "--incident-id",
            "INC-1",
            "--reference-time",
            "2026-11-20T10:45:00",
        ],
    )

    assert salida.exit_code == 0
    cuerpo = json.loads(salida.stdout)
    assert cuerpo["elapsed_minutes"] == 45
    assert cuerpo["window"] == "24x7"


def test_sla_con_identificador_vacio_sale_con_2(
    base_cli: Path, runner_cli: CliRunner
) -> None:
    """FR-017: el identificador vacío reserva `SLA_ID_VACIO` para la consola."""
    salida = runner_cli.invoke(app, ["sla", "--incident-id", "   "])

    assert salida.exit_code == 2
    assert salida.stdout.strip() == ""
    assert "SLA_ID_VACIO" in _error(salida)


def test_sla_inexistente_sale_con_1(
    base_cli: Path, runner_cli: CliRunner
) -> None:
    """FR-023: un incidente inexistente es salida 1 sin documento parcial."""
    salida = runner_cli.invoke(app, ["sla", "--incident-id", "INC-404"])

    assert salida.exit_code == 1
    assert salida.stdout.strip() == ""
    assert "SLA_INCIDENTE_NO_ENCONTRADO" in _error(salida)


def test_sla_con_fecha_invalida_sale_con_2(
    base_cli: Path, runner_cli: CliRunner
) -> None:
    """FR-024: una referencia ilegible es entrada inválida con salida 2."""
    _crear(runner_cli)

    salida = runner_cli.invoke(
        app,
        [
            "sla",
            "--incident-id",
            "INC-1",
            "--reference-time",
            "2026-11-20 10:00:00",
        ],
    )

    assert salida.exit_code == 2
    assert salida.stdout.strip() == ""
    assert "SLA_REFERENCIA_INVALIDA" in _error(salida)
