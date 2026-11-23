"""Pruebas de aceptación BDD de H004: salud real con paridad HTTP/CLI.

Cada escenario sigue Dado / Cuando / Entonces (Constitución §VII) y usa dobles
en memoria del puerto: la suite no necesita Docker, red ni una base real
(RNF-001). La verificación estructural de `Dockerfile`, `.dockerignore`,
`docker-compose.yml` y `.env.example` se hace leyendo texto, sin PyYAML.
"""

import json
from pathlib import Path
from typing import Any, Optional, Sequence

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from src.adapters.inbound.api.app import create_app
from src.adapters.inbound.cli import app as cli_app
from src.application.services import IncidentService
from src.domain.models import Incident

RAIZ = Path(__file__).resolve().parent.parent
RUTA_HEALTH = "/health"
RUTA_TRIAGE = "/api/v1/incidents/triage"
RUTA_RESUMEN = "/api/v1/incidents/summary"
RUTA_ALTA = "/api/v1/incidents"
RUTA_SLA = "/api/v1/incidents/{incident_id}/sla"

DOC_CONECTADO = {"status": "ok", "database": "connected"}
DOC_NO_DISPONIBLE = {"status": "error", "database": "unavailable"}
TEXTO_P0 = "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta."


class _RepositorioDeSalud:
    """Doble del puerto que informa siempre el mismo estado de conectividad."""

    def __init__(self, conectado: bool = True) -> None:
        self.conectado = conectado
        self.consultas = 0

    def save_incident(self, incident: Incident) -> None:
        return None

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        return None

    def find_open_duplicates(self, incident: Incident) -> Sequence[Incident]:
        return []

    def list_active_incidents(
        self, component_filter: Optional[str]
    ) -> Sequence[Incident]:
        return []

    def check_health(self) -> bool:
        self.consultas += 1
        return self.conectado


class _RepositorioCaido:
    """Doble cuyo motor no responde: toda operación lanza un error de conexión."""

    MENSAJE = "connection refused: host interno no disponible"

    def save_incident(self, incident: Incident) -> None:
        raise ConnectionError(self.MENSAJE)

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        raise ConnectionError(self.MENSAJE)

    def find_open_duplicates(self, incident: Incident) -> Sequence[Incident]:
        raise ConnectionError(self.MENSAJE)

    def list_active_incidents(
        self, component_filter: Optional[str]
    ) -> Sequence[Incident]:
        raise ConnectionError(self.MENSAJE)

    def check_health(self) -> bool:
        return False


def _error(resultado: Any) -> str:
    return (resultado.stderr or "") + (resultado.output or "")


def _servicio(conectado: bool = True) -> IncidentService:
    return IncidentService(_RepositorioDeSalud(conectado))


def _cli_con_servicio(
    monkeypatch: pytest.MonkeyPatch, servicio: IncidentService
) -> None:
    """Sustituye la composición de la CLI por un servicio con doble."""
    monkeypatch.setattr(
        "src.adapters.inbound.cli.build_incident_service", lambda: servicio
    )


# ---------------------------------------------------------------------------
# US1 · Saber si el servicio puede atender contra su base real
# ---------------------------------------------------------------------------


def test_bdd_e01_el_servicio_confirma_que_su_base_responde() -> None:
    """Dado un servicio con base viva, Cuando se consulta /health, Entonces 200."""
    repositorio = _RepositorioDeSalud(True)
    cliente = TestClient(create_app(IncidentService(repositorio)))

    respuesta = cliente.get(RUTA_HEALTH)

    assert respuesta.status_code == 200
    assert respuesta.json() == DOC_CONECTADO
    assert respuesta.headers["content-type"].startswith("application/json")
    assert respuesta.headers["cache-control"] == "no-store"
    assert repositorio.consultas == 1


def test_bdd_e02_la_consola_confirma_la_misma_conectividad(
    monkeypatch: pytest.MonkeyPatch, runner_cli: CliRunner
) -> None:
    """Dado el mismo servicio, Cuando se ejecuta `health`, Entonces documento y 0."""
    _cli_con_servicio(monkeypatch, _servicio(True))

    salida = runner_cli.invoke(cli_app, ["health"])

    assert salida.exit_code == 0
    assert json.loads(salida.stdout) == DOC_CONECTADO
    assert (salida.stderr or "").strip() == ""


def test_bdd_e03_una_base_inaccesible_se_informa_como_no_disponible() -> None:
    """Dado un servicio sin base, Cuando se consulta /health, Entonces 503."""
    repositorio = _RepositorioDeSalud(False)
    cliente = TestClient(create_app(IncidentService(repositorio)))

    respuesta = cliente.get(RUTA_HEALTH)

    assert respuesta.status_code == 503
    assert respuesta.json() == DOC_NO_DISPONIBLE
    assert respuesta.headers["content-type"].startswith("application/json")
    assert respuesta.headers["cache-control"] == "no-store"
    texto = respuesta.text.lower()
    assert "traceback" not in texto
    assert "password" not in texto
    assert "host" not in texto


def test_bdd_e04_la_consola_informa_la_indisponibilidad(
    monkeypatch: pytest.MonkeyPatch, runner_cli: CliRunner
) -> None:
    """Dado el mismo servicio sin base, Cuando se ejecuta `health`, Entonces 1."""
    _cli_con_servicio(monkeypatch, _servicio(False))

    salida = runner_cli.invoke(cli_app, ["health"])

    assert salida.exit_code == 1
    assert json.loads(salida.stdout) == DOC_NO_DISPONIBLE
    assert (salida.stderr or "").strip() == ""
    assert "traceback" not in _error(salida).lower()


def test_la_configuracion_invalida_sale_2_sin_documento(
    monkeypatch: pytest.MonkeyPatch, runner_cli: CliRunner
) -> None:
    """FR-018: un esquema no admitido no produce documento de salud."""
    monkeypatch.setenv(
        "DATABASE_URL", "postgres://incidentops:clave-secreta@localhost:5432/base"
    )

    salida = runner_cli.invoke(cli_app, ["health"])

    assert salida.exit_code == 2
    assert salida.stdout.strip() == ""
    documento = json.loads(salida.stderr)
    assert documento["code"] == "CONFIG_DATABASE_URL_INVALIDA"
    assert documento["status"] == 422
    assert documento["errors"][0]["field"] == "DATABASE_URL"
    assert "clave-secreta" not in salida.stderr
    assert "traceback" not in salida.stderr.lower()


def test_el_fallo_interno_del_comando_sale_1_sin_traza(
    monkeypatch: pytest.MonkeyPatch, runner_cli: CliRunner
) -> None:
    """FR-003: un fallo ajeno a la conectividad es `HEALTH_ERROR_INTERNO`."""

    def _explota() -> IncidentService:
        raise RuntimeError("detalle interno que no debe filtrarse")

    monkeypatch.setattr(
        "src.adapters.inbound.cli.build_incident_service", _explota
    )

    salida = runner_cli.invoke(cli_app, ["health"])

    assert salida.exit_code == 1
    assert salida.stdout.strip() == ""
    assert "HEALTH_ERROR_INTERNO" in salida.stderr
    assert "detalle interno" not in salida.stderr
    assert "traceback" not in salida.stderr.lower()


# ---------------------------------------------------------------------------
# US2 · El mismo servicio sin infraestructura y con infraestructura
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("conectado", [True, False])
def test_bdd_e05_ambos_canales_coinciden_al_informar_la_salud(
    monkeypatch: pytest.MonkeyPatch,
    runner_cli: CliRunner,
    conectado: bool,
) -> None:
    """Dado un estado único, Cuando se consulta por HTTP y consola, Entonces iguales."""
    servicio = _servicio(conectado)
    cliente = TestClient(create_app(servicio))
    _cli_con_servicio(monkeypatch, servicio)

    por_http = cliente.get(RUTA_HEALTH)
    por_consola = runner_cli.invoke(cli_app, ["health"])

    assert por_http.json() == json.loads(por_consola.stdout)
    assert por_http.status_code == (200 if conectado else 503)
    assert por_consola.exit_code == (0 if conectado else 1)
    assert set(por_http.json()) == {"status", "database"}


def test_bdd_e06_el_desarrollo_local_sigue_funcionando_sin_base_dedicada(
    monkeypatch: pytest.MonkeyPatch, runner_cli: CliRunner
) -> None:
    """Dado un entorno sin `DATABASE_URL`, Cuando se consulta salud, Entonces connected."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    cliente = TestClient(create_app())

    por_http = cliente.get(RUTA_HEALTH)
    por_consola = runner_cli.invoke(cli_app, ["health"])

    assert por_http.status_code == 200
    assert por_http.json() == DOC_CONECTADO
    assert por_consola.exit_code == 0
    assert json.loads(por_consola.stdout) == DOC_CONECTADO


def test_el_motor_caido_no_cambia_el_error_generico_de_negocio(
    monkeypatch: pytest.MonkeyPatch, runner_cli: CliRunner
) -> None:
    """FR-012: sólo `/health` traduce la caída a 503; el negocio sigue genérico.

    El triaje es estático (H001) y no toca el almacenamiento, por lo que sigue
    respondiendo igual; resumen, alta y SLA conservan su error interno genérico
    sin códigos nuevos ni detalles del motor.
    """
    servicio = IncidentService(_RepositorioCaido())
    cliente = TestClient(create_app(servicio), raise_server_exceptions=False)
    _cli_con_servicio(monkeypatch, servicio)

    triaje = cliente.post(RUTA_TRIAGE, json={"incident_id": "INC-1", "raw_text": TEXTO_P0})
    resumen = cliente.get(RUTA_RESUMEN, params={"reference_time": "2026-11-20T12:00:00"})
    alta = cliente.post(
        RUTA_ALTA, json={"incident_id": "INC-1", "raw_text": TEXTO_P0}
    )
    sla = cliente.get(
        RUTA_SLA.format(incident_id="INC-1"),
        params={"reference_time": "2026-11-20T12:00:00"},
    )

    assert triaje.status_code == 200
    assert resumen.status_code == 500
    assert resumen.json()["code"] == "SUMMARY_ERROR_INTERNO"
    assert alta.status_code == 500
    assert alta.json()["code"] == "CREATE_ERROR_INTERNO"
    assert sla.status_code == 500
    assert sla.json()["code"] == "SLA_ERROR_INTERNO"
    for respuesta in (resumen, alta, sla):
        assert _RepositorioCaido.MENSAJE not in respuesta.text
        assert "host interno" not in respuesta.text

    triaje_cli = runner_cli.invoke(
        cli_app, ["triage", "--incident-id", "INC-1", "--raw-text", TEXTO_P0]
    )
    resumen_cli = runner_cli.invoke(cli_app, ["summary"])
    alta_cli = runner_cli.invoke(
        cli_app, ["create", "--incident-id", "INC-1", "--raw-text", TEXTO_P0]
    )
    sla_cli = runner_cli.invoke(cli_app, ["sla", "--incident-id", "INC-1"])

    assert triaje_cli.exit_code == 0
    assert resumen_cli.exit_code == 1
    assert "SUMMARY_ERROR_INTERNO" in _error(resumen_cli)
    assert alta_cli.exit_code == 1
    assert "CREATE_ERROR_INTERNO" in _error(alta_cli)
    assert sla_cli.exit_code == 1
    assert "SLA_ERROR_INTERNO" in _error(sla_cli)
    for salida in (resumen_cli, alta_cli, sla_cli):
        assert _RepositorioCaido.MENSAJE not in _error(salida)
        assert "host interno" not in _error(salida)


# ---------------------------------------------------------------------------
# Empaquetado y despliegue de referencia (verificación estructural)
# ---------------------------------------------------------------------------


def _leer(nombre: str) -> str:
    return (RAIZ / nombre).read_text(encoding="utf-8")


def test_el_dockerfile_es_multietapa_reproducible_y_sin_privilegios() -> None:
    """FR-013/RNF-007: slim, lockfile congelado, usuario no root y Uvicorn."""
    dockerfile = _leer("Dockerfile")

    assert "python:3.12-slim" in dockerfile
    assert "uv sync --frozen" in dockerfile
    assert "--no-dev" in dockerfile
    assert dockerfile.count("FROM ") >= 2
    assert "EXPOSE 8000" in dockerfile
    assert "uvicorn" in dockerfile.lower()
    assert "src.adapters.inbound.api.app:app" in dockerfile
    usuario = [linea for linea in dockerfile.splitlines() if linea.strip().startswith("USER ")]
    assert usuario
    assert "10001" in usuario[-1]
    assert "ARG" not in dockerfile or "PASSWORD" not in dockerfile


def test_el_dockerignore_excluye_secretos_y_artefactos() -> None:
    """FR-016/RNF-007: la imagen no arrastra secretos, VCS ni pruebas."""
    patrones = {
        linea.strip()
        for linea in _leer(".dockerignore").splitlines()
        if linea.strip() and not linea.strip().startswith("#")
    }

    for obligatorio in (
        ".git",
        ".env",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "tests/",
        "specs/",
        "docs/",
        "data/",
        "*.db",
        "CONTEXT_LOG.md",
    ):
        assert obligatorio in patrones, obligatorio
    assert "src/" not in patrones
    assert "pyproject.toml" not in patrones
    assert "uv.lock" not in patrones


def test_el_compose_define_db_y_api_con_arranque_ordenado() -> None:
    """FR-014: base sana antes que la API, volumen nombrado y sin publicar la base."""
    compose = _leer("docker-compose.yml")

    assert "postgres:16-alpine" in compose
    assert "pg_isready" in compose
    assert "condition: service_healthy" in compose
    assert "incidentops_pgdata" in compose
    assert "PGDATA" in compose
    assert "5432:5432" not in compose
    assert "api" in compose and "db" in compose
    assert "/health" in compose
    assert "urllib.request" in compose
    assert "API_PORT" in compose
    assert "depends_on" in compose


def test_el_env_example_documenta_marcadores_no_secretos() -> None:
    """FR-015: credenciales por entorno con marcadores locales documentados."""
    ejemplo = _leer(".env.example")

    for variable in (
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "DATABASE_URL",
        "API_PORT",
    ):
        assert variable in ejemplo
    assert "codificar" in ejemplo.lower() or "url" in ejemplo.lower()
