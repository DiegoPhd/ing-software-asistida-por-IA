"""Suite de contrato del `IncidentRepositoryPort` sobre SQLite y PostgreSQL (C-02).

La misma prueba corre contra ambos motores y demuestra la paridad exigida por
RNF-006: cinco métodos del puerto, conflicto estricto sin sobrescritura, filtro
de activos y componente, candidatos de duplicado sin similitud, formato
temporal con microsegundos y errores de validación equivalentes. Sin
`TEST_POSTGRES_URL` los casos PostgreSQL se omiten y la suite base sigue verde
(RNF-001).
"""

import os
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import pytest

from src.adapters.outbound.postgres_repository import PostgresIncidentRepository
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.services import IncidentAlreadyExistsError
from src.domain.models import Incident, InvalidIncidentError

try:  # el caso PostgreSQL es opcional en la suite base
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - psycopg es dependencia principal
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]

RAIZ = Path(__file__).resolve().parent.parent.parent
TEST_POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
PATRON_TEMPORAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}$")
BASE = datetime(2026, 11, 20, 10, 0, 0, 123456)
TEXTO = "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta."


def _sufijo() -> str:
    return uuid.uuid4().hex[:12]


def _componente() -> str:
    return f"componente-{_sufijo()}"


def _incidente(
    incident_id: Optional[str] = None,
    component: Optional[str] = None,
    severity: str = "P0",
    status: str = "OPEN",
    created_at: datetime = BASE,
    resolved_at: Optional[datetime] = None,
    raw_text: Optional[str] = TEXTO,
    recommended_team: Optional[str] = None,
    duplicate_group_key: Optional[str] = None,
) -> Incident:
    return Incident(
        incident_id=incident_id or f"INC-{_sufijo()}",
        title="Incidente de contrato",
        component=component or _componente(),
        severity=severity,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        created_at=created_at,
        resolved_at=resolved_at,
        raw_text=raw_text,
        recommended_team=recommended_team,  # type: ignore[arg-type]
        duplicate_group_key=duplicate_group_key,
    )


@pytest.fixture(params=["sqlite", "postgresql"])
def repositorio(request: pytest.FixtureRequest):
    """Instancia el adaptador del motor parametrizado."""
    if request.param == "sqlite":
        return SQLiteIncidentRepository()

    if not TEST_POSTGRES_URL:
        pytest.skip("TEST_POSTGRES_URL no definida: se omite PostgreSQL")
    if psycopg is None:  # pragma: no cover - nunca con la dependencia instalada
        pytest.skip("psycopg no está disponible")
    return PostgresIncidentRepository(TEST_POSTGRES_URL)


def _texto_crudo(repositorio: object, incident_id: str) -> Tuple[str, Optional[str]]:
    """Lee las columnas temporales tal como quedaron persistidas."""
    if isinstance(repositorio, SQLiteIncidentRepository):
        fila = repositorio.conn.execute(
            "SELECT created_at, resolved_at FROM incidents WHERE incident_id = ?",
            (incident_id,),
        ).fetchone()
        assert fila is not None
        return fila["created_at"], fila["resolved_at"]

    assert TEST_POSTGRES_URL is not None
    with psycopg.connect(TEST_POSTGRES_URL, row_factory=dict_row) as conexion:  # type: ignore[union-attr]
        fila = conexion.execute(
            "SELECT created_at, resolved_at FROM incidents WHERE incident_id = %s",
            (incident_id,),
        ).fetchone()
    assert fila is not None
    return fila["created_at"], fila["resolved_at"]


def test_los_cinco_metodos_del_puerto_responden(repositorio: object) -> None:
    """El adaptador cumple la firma completa del contrato de salida."""
    incidente = _incidente()
    repositorio.save_incident(incidente)  # type: ignore[attr-defined]

    assert repositorio.get_incident(incidente.incident_id) == incidente  # type: ignore[attr-defined]
    assert repositorio.get_incident("INC-INEXISTENTE") is None  # type: ignore[attr-defined]
    candidatos = repositorio.find_open_duplicates(incidente)  # type: ignore[attr-defined]
    assert incidente.incident_id not in {  # type: ignore[attr-defined]
        candidato.incident_id for candidato in candidatos
    }
    assert incidente in repositorio.list_active_incidents(  # type: ignore[attr-defined]
        incidente.component
    )
    assert repositorio.check_health() is True  # type: ignore[attr-defined]


def test_conflicto_estricto_sin_sobrescribir(repositorio: object) -> None:
    """FR-008: el `INSERT` estricto no reemplaza la fila previa."""
    original = _incidente(raw_text=TEXTO)
    repositorio.save_incident(original)  # type: ignore[attr-defined]

    with pytest.raises(IncidentAlreadyExistsError):
        repositorio.save_incident(  # type: ignore[attr-defined]
            _incidente(
                incident_id=original.incident_id,
                component="otro-componente",
                severity="P3",
                created_at=BASE + timedelta(hours=1),
                raw_text="Texto completamente distinto.",
            )
        )

    assert repositorio.get_incident(original.incident_id) == original  # type: ignore[attr-defined]


def test_lista_solo_activos_y_filtra_por_componente(repositorio: object) -> None:
    """FR-008: filtro de estado activo y componente sin cálculo de SLA."""
    componente = _componente()
    abierto = _incidente(component=componente, status="OPEN")
    en_curso = _incidente(
        component=componente, status="IN_PROGRESS", severity="P1"
    )
    resuelto = _incidente(
        component=componente,
        status="RESOLVED",
        severity="P2",
        resolved_at=BASE + timedelta(minutes=10),
    )
    ajeno = _incidente(status="OPEN")
    for incidente in (abierto, en_curso, resuelto, ajeno):
        repositorio.save_incident(incidente)  # type: ignore[attr-defined]

    filtrados = repositorio.list_active_incidents(componente)  # type: ignore[attr-defined]
    todos = repositorio.list_active_incidents(None)  # type: ignore[attr-defined]

    assert {incidente.incident_id for incidente in filtrados} == {
        abierto.incident_id,
        en_curso.incident_id,
    }
    assert {incidente.incident_id for incidente in todos} >= {
        abierto.incident_id,
        en_curso.incident_id,
        ajeno.incident_id,
    }
    assert resuelto.incident_id not in {
        incidente.incident_id for incidente in todos
    }


def test_candidatos_de_duplicado_sin_similitud(repositorio: object) -> None:
    """H003: el adaptador filtra estructura; la similitud es del dominio."""
    componente = _componente()
    similar = _incidente(component=componente, raw_text=TEXTO)
    distinto = _incidente(
        component=componente, raw_text="pago " + "a" * 400
    )
    otro_componente = _incidente(raw_text=TEXTO)
    resuelto = _incidente(
        component=componente,
        status="RESOLVED",
        resolved_at=BASE + timedelta(minutes=5),
    )
    for incidente in (similar, distinto, otro_componente, resuelto):
        repositorio.save_incident(incidente)  # type: ignore[attr-defined]

    candidatos = repositorio.find_open_duplicates(  # type: ignore[attr-defined]
        _incidente(component=componente)
    )

    assert {candidato.incident_id for candidato in candidatos} == {
        similar.incident_id,
        distinto.incident_id,
    }


def test_el_texto_temporal_usa_microsegundos(repositorio: object) -> None:
    """FR-009: `YYYY-MM-DDTHH:MM:SS.ffffff` en ambos motores."""
    incidente = _incidente(
        created_at=datetime(2026, 11, 20, 10, 0, 0),
        resolved_at=datetime(2026, 11, 20, 10, 0, 30, 654321),
        status="RESOLVED",
    )
    repositorio.save_incident(incidente)  # type: ignore[attr-defined]

    creado, resuelto = _texto_crudo(repositorio, incidente.incident_id)

    assert PATRON_TEMPORAL.match(creado), creado
    assert resuelto is not None
    assert PATRON_TEMPORAL.match(resuelto), resuelto
    assert repositorio.get_incident(incidente.incident_id) == incidente  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "incidente",
    [
        _incidente(incident_id="   "),
        _incidente(component="   "),
        _incidente(severity="P9"),
        _incidente(status="RESOLVED", resolved_at=None),
        _incidente(status="INVESTIGATING"),
        _incidente(recommended_team="Equipo-Inventado"),
    ],
    ids=[
        "id-vacio",
        "componente-vacio",
        "severidad-sin-politica",
        "terminal-sin-resolucion",
        "estado-desconocido",
        "equipo-fuera-del-catalogo",
    ],
)
def test_errores_de_validacion_equivalentes(repositorio: object, incidente: Incident) -> None:
    """Los invariantes de escritura se validan igual en ambos motores."""
    with pytest.raises(InvalidIncidentError):
        repositorio.save_incident(incidente)  # type: ignore[attr-defined]


def test_el_adaptador_no_ordena_ni_calcula_sla() -> None:
    """El adaptador no ordena, no calcula SLA, similitud ni claves de grupo."""
    for relativa in (
        "sqlite_repository.py",
        "postgres_repository.py",
    ):
        codigo = (RAIZ / "src" / "adapters" / "outbound" / relativa).read_text(
            encoding="utf-8"
        )
        assert "ORDER BY" not in codigo.upper(), relativa
        assert "evaluate_sla" not in codigo, relativa
        assert "SequenceMatcher" not in codigo, relativa
