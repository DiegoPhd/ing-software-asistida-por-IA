"""Pruebas del contrato de configuración `DATABASE_URL` (C-01).

La fábrica es el único punto que interpreta el DSN: selecciona SQLite o
PostgreSQL, inyecta el reloj y falla antes de abrir conexión ante cualquier
configuración no admitida. Construir el repositorio PostgreSQL no exige un
servidor vivo, de modo que la matriz se prueba sin Docker.
"""

from pathlib import Path

import pytest

from src.adapters.outbound.factory import (
    ConfigurationError,
    build_incident_service,
    create_repository,
    resolve_database_path,
)
from src.adapters.outbound.postgres_repository import PostgresIncidentRepository
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.ports import IncidentRepositoryPort

# Puerto local sin servicio: la conexión se rechaza de inmediato y el
# constructor no debe propagar el fallo (arranque tolerante, FR-010).
DSN_LOCAL_NO_ALCANZABLE = "postgresql://incidentops:clave@127.0.0.1:1/incidentops"


@pytest.fixture(autouse=True)
def _sin_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla cada prueba de la variable de entorno real."""
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_selecciona_adaptador_por_database_url(tmp_path: Path) -> None:
    """FR-006: ausencia/memoria → SQLite; archivo → SQLite; DSN → PostgreSQL."""
    ruta = tmp_path / "seleccion.db"

    memoria = create_repository()
    en_memoria = create_repository("sqlite:///:memory:")
    en_archivo = create_repository(f"sqlite:///{ruta}")
    postgres = create_repository(DSN_LOCAL_NO_ALCANZABLE)

    assert isinstance(memoria, SQLiteIncidentRepository)
    assert isinstance(en_memoria, SQLiteIncidentRepository)
    assert isinstance(en_archivo, SQLiteIncidentRepository)
    assert isinstance(postgres, PostgresIncidentRepository)
    assert ruta.exists()


def test_ambos_adaptadores_cumplen_el_puerto() -> None:
    """El puerto se cumple estructuralmente en los dos motores."""
    assert isinstance(create_repository("sqlite:///:memory:"), IncidentRepositoryPort)
    assert isinstance(create_repository(DSN_LOCAL_NO_ALCANZABLE), IncidentRepositoryPort)


def test_construir_postgres_no_exige_un_servidor_vivo() -> None:
    """FR-010: el fallo de conexión no impide construir ni informar salud."""
    repositorio = PostgresIncidentRepository(DSN_LOCAL_NO_ALCANZABLE)

    assert repositorio.check_health() is False


def test_la_fabrica_inyecta_el_reloj_y_el_repositorio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    servicio = build_incident_service("sqlite:///:memory:")

    assert servicio.check_health() is True


@pytest.mark.parametrize(
    "url",
    [
        "mysql://localhost/incidentops",
        "sqlite://",
        "sqlite:///",
        "postgres://localhost/incidentops",
        "postgresql://",
        "",
        "   ",
    ],
)
def test_la_configuracion_no_admitida_falla_sin_abrir_conexion(url: str) -> None:
    """FR-006/SC-007: vacío, alias y esquemas desconocidos no caen a memoria."""
    with pytest.raises(ConfigurationError):
        create_repository(url)


def test_el_error_de_configuracion_solo_cita_el_esquema() -> None:
    """RNF-008: el mensaje nunca incluye credenciales ni el DSN completo."""
    with pytest.raises(ConfigurationError) as excinfo:
        create_repository("mysql://usuario:clave-secreta@db-interno:3306/base")

    mensaje = str(excinfo.value)
    assert "'mysql'" in mensaje
    assert "clave-secreta" not in mensaje
    assert "db-interno" not in mensaje
    assert "mysql://usuario:clave-secreta@db-interno:3306/base" not in mensaje


def test_la_variable_ausente_usa_memoria(monkeypatch: pytest.MonkeyPatch) -> None:
    assert resolve_database_path() == ":memory:"
    assert isinstance(create_repository(), SQLiteIncidentRepository)


def test_la_variable_vacia_es_configuracion_invalida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "   ")

    with pytest.raises(ConfigurationError):
        create_repository()
    with pytest.raises(ConfigurationError):
        resolve_database_path()


def test_la_variable_postgresql_selecciona_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", DSN_LOCAL_NO_ALCANZABLE)

    assert isinstance(create_repository(), PostgresIncidentRepository)


def test_resolve_database_path_conserva_las_rutas_sqlite(tmp_path: Path) -> None:
    """Las rutas SQLite de H002 no cambian."""
    ruta = tmp_path / "helpers.db"

    assert resolve_database_path("sqlite:///:memory:") == ":memory:"
    assert resolve_database_path(f"sqlite:///{ruta}") == str(ruta)
    with pytest.raises(ConfigurationError):
        resolve_database_path(DSN_LOCAL_NO_ALCANZABLE)
