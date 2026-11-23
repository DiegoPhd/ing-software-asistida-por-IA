"""Pruebas del adaptador SQLite de H002.

Cubren el cumplimiento del puerto, la consulta única, el uso del índice, la
migración de `raw_text` y la equivalencia con un doble del puerto (FR-018).
"""

import inspect
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Sequence

import pytest

from src.adapters.outbound.factory import (
    ConfigurationError,
    create_repository,
    resolve_database_path,
)
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.application.ports import IncidentRepositoryPort
from src.application.services import (
    IncidentAlreadyExistsError,
    IncidentService,
)
from src.domain.models import Incident, InvalidIncidentError
from src.domain.sla_calculator import summarize_active_incidents

REFERENCIA = datetime(2026, 11, 20, 12, 0, 0)
METODOS_DEL_PUERTO = (
    "save_incident",
    "get_incident",
    "find_open_duplicates",
    "list_active_incidents",
    "check_health",
)


def _incidente(
    incident_id: str = "INC-1",
    component: str = "payments-gateway",
    severity: str = "P0",
    status: str = "OPEN",
    created_at: Optional[datetime] = None,
    resolved_at: Optional[datetime] = None,
) -> Incident:
    return Incident(
        incident_id=incident_id,
        title=f"Incidente {incident_id}",
        component=component,
        severity=severity,
        status=status,
        created_at=created_at or REFERENCIA - timedelta(minutes=30),
        resolved_at=resolved_at,
    )


class _RepositorioEnMemoria:
    """Doble del puerto con la misma semántica que el adaptador SQLite."""

    def __init__(self, incidentes: Sequence[Incident]) -> None:
        self._incidentes: List[Incident] = list(incidentes)

    def save_incident(self, incident: Incident) -> None:
        self._incidentes.append(incident)

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        return next(
            (
                incidente
                for incidente in self._incidentes
                if incidente.incident_id == incident_id
            ),
            None,
        )

    def find_open_duplicates(self, incident: Incident) -> Sequence[Incident]:
        return [
            otro
            for otro in self._incidentes
            if otro.status in ("OPEN", "IN_PROGRESS")
            and otro.component == incident.component
            and otro.incident_id != incident.incident_id
        ]

    def list_active_incidents(
        self, component_filter: Optional[str]
    ) -> Sequence[Incident]:
        return [
            incidente
            for incidente in self._incidentes
            if incidente.status in ("OPEN", "IN_PROGRESS")
            and (component_filter is None or incidente.component == component_filter)
        ]

    def check_health(self) -> bool:
        return True


def test_el_repositorio_cumple_el_puerto_por_firma() -> None:
    """D3: `runtime_checkable` más comparación estructural de firmas."""
    repositorio = SQLiteIncidentRepository()

    assert isinstance(repositorio, IncidentRepositoryPort)
    for nombre in METODOS_DEL_PUERTO:
        firma_puerto = inspect.signature(getattr(IncidentRepositoryPort, nombre))
        firma_adaptador = inspect.signature(getattr(SQLiteIncidentRepository, nombre))
        assert list(firma_adaptador.parameters) == list(firma_puerto.parameters), nombre
        assert firma_adaptador.return_annotation == firma_puerto.return_annotation, nombre


def test_el_resumen_emite_una_sola_consulta_sin_n_mas_uno() -> None:
    """D4: una sola sentencia por resumen, contada sobre la conexión real."""
    repositorio = SQLiteIncidentRepository()
    repositorio.save_incident(_incidente())
    repositorio.save_incident(
        _incidente("INC-2", component="auth-identity", severity="P1", status="IN_PROGRESS")
    )

    sentencias: List[str] = []
    repositorio.conn.set_trace_callback(sentencias.append)
    try:
        resumen = IncidentService(repositorio).get_active_incidents_summary(
            reference_time=REFERENCIA, component_filter="payments-gateway"
        )
    finally:
        repositorio.conn.set_trace_callback(None)

    assert resumen.total_active == 1
    assert len(sentencias) == 1
    assert "FROM incidents" in sentencias[0]


def test_el_filtro_por_componente_usa_el_indice_compuesto() -> None:
    """T034: el plan de consulta filtrado menciona el índice compuesto."""
    repositorio = SQLiteIncidentRepository()
    repositorio.seed_synthetic_incidents(500)

    plan = repositorio.query_plan("payments-gateway")

    assert any("idx_incidents_component_status" in linea for linea in plan)


def test_migra_raw_text_en_bases_heredadas(tmp_path: Path) -> None:
    """Compatibilidad con bases de Semana 1 sin columna `raw_text`."""
    ruta = tmp_path / "heredada.db"
    conexion = sqlite3.connect(ruta)
    conexion.execute(
        """
        CREATE TABLE incidents (
            incident_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            component TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )
        """
    )
    conexion.execute(
        "INSERT INTO incidents VALUES "
        "('INC-1', 'Heredado', 'payments-gateway', 'P0', 'OPEN', "
        "'2026-11-20T11:00:00', NULL)"
    )
    conexion.commit()
    conexion.close()

    repositorio = SQLiteIncidentRepository(str(ruta))
    columnas = {
        fila["name"] for fila in repositorio.conn.execute("PRAGMA table_info(incidents)")
    }

    assert "raw_text" in columnas
    assert repositorio.get_incident("INC-1") is not None


@pytest.mark.parametrize(
    "url",
    ["postgresql://localhost/incidentops", "mysql://localhost/incidentops", "sqlite://"],
)
def test_rechaza_database_url_con_esquema_no_soportado(url: str) -> None:
    with pytest.raises(ConfigurationError):
        create_repository(url)


def test_resuelve_memoria_y_archivo(tmp_path: Path) -> None:
    assert resolve_database_path("") == ":memory:"
    assert resolve_database_path("sqlite:///:memory:") == ":memory:"

    ruta = tmp_path / "incidentops.db"
    assert resolve_database_path(f"sqlite:///{ruta}") == str(ruta)

    repositorio = create_repository(f"sqlite:///{ruta}")
    assert repositorio.check_health() is True


@pytest.mark.parametrize(
    ("incidente", "campo"),
    [
        (_incidente(incident_id="   "), "incident_id"),
        (_incidente(component="  "), "component"),
    ],
)
def test_rechaza_identificador_o_componente_vacios(
    incidente: Incident, campo: str
) -> None:
    repositorio = SQLiteIncidentRepository()

    with pytest.raises(InvalidIncidentError):
        repositorio.save_incident(incidente)


@pytest.mark.parametrize("status", ["RESOLVED", "CLOSED"])
def test_rechaza_terminal_sin_resolved_at(status: str) -> None:
    repositorio = SQLiteIncidentRepository()

    with pytest.raises(InvalidIncidentError):
        repositorio.save_incident(_incidente(status=status))


def test_rechaza_fechas_con_zona_horaria() -> None:
    repositorio = SQLiteIncidentRepository()
    con_zona = datetime(2026, 11, 20, 11, 0, 0).astimezone()

    with pytest.raises(InvalidIncidentError):
        repositorio.save_incident(_incidente(created_at=con_zona))


def test_el_resumen_no_modifica_datos() -> None:
    """FR-013: consultar el resumen no escribe en la base."""
    repositorio = SQLiteIncidentRepository()
    repositorio.save_incident(_incidente())
    antes = repositorio.conn.total_changes

    IncidentService(repositorio).get_active_incidents_summary(
        reference_time=REFERENCIA
    )

    assert repositorio.conn.total_changes == antes


def test_el_resumen_es_equivalente_entre_adaptador_y_doble() -> None:
    """FR-018: cambiar el origen de datos no altera totales ni detalle."""
    incidentes = [
        _incidente("INC-1", "payments-gateway", "P0", "OPEN"),
        _incidente(
            "INC-2",
            "payments-gateway",
            "P0",
            "OPEN",
            created_at=REFERENCIA - timedelta(minutes=70),
        ),
        _incidente("INC-3", "auth-identity", "P1", "IN_PROGRESS"),
        _incidente(
            "INC-4",
            "auth-identity",
            "P1",
            "RESOLVED",
            resolved_at=REFERENCIA - timedelta(minutes=5),
        ),
    ]
    repositorio = SQLiteIncidentRepository()
    for incidente in incidentes:
        repositorio.save_incident(incidente)
    doble = _RepositorioEnMemoria(incidentes)

    resumen_sqlite = IncidentService(repositorio).get_active_incidents_summary(
        reference_time=REFERENCIA
    )
    resumen_doble = IncidentService(doble).get_active_incidents_summary(
        reference_time=REFERENCIA
    )

    assert resumen_sqlite == resumen_doble


def test_consulta_puntual_y_candidatos_de_duplicados() -> None:
    repositorio = SQLiteIncidentRepository()
    repositorio.save_incident(_incidente("INC-1"))
    repositorio.save_incident(_incidente("INC-2"))
    repositorio.save_incident(_incidente("INC-3", component="auth-identity"))

    assert repositorio.get_incident("INC-2") is not None
    assert repositorio.get_incident("INC-404") is None

    candidatos = repositorio.find_open_duplicates(_incidente("INC-1"))
    assert [candidato.incident_id for candidato in candidatos] == ["INC-2"]


def test_ida_y_vuelta_de_equipo_y_clave_de_grupo() -> None:
    """FR-012: las columnas nuevas se persisten y se recuperan sin alterarse."""
    repositorio = SQLiteIncidentRepository()
    incidente = Incident(
        incident_id="INC-1",
        title="Pagos caídos",
        component="payments-gateway",
        severity="P0",
        status="OPEN",
        created_at=REFERENCIA - timedelta(minutes=30),
        raw_text="Pasarela de pagos caída.",
        recommended_team="Backend-Core",
        duplicate_group_key="INC-0",
    )

    repositorio.save_incident(incidente)

    assert repositorio.get_incident("INC-1") == incidente


def test_migra_columnas_nuevas_en_bases_de_h002(tmp_path: Path) -> None:
    """D6: una base anterior arranca, migra columnas y crea el índice nuevo."""
    ruta = tmp_path / "h002.db"
    conexion = sqlite3.connect(ruta)
    conexion.execute(
        """
        CREATE TABLE incidents (
            incident_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            component TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            resolved_at TEXT,
            raw_text TEXT
        )
        """
    )
    conexion.execute(
        "INSERT INTO incidents VALUES "
        "('INC-1', 'Heredado', 'payments-gateway', 'P0', 'OPEN', "
        "'2026-11-20T11:00:00', NULL, NULL)"
    )
    conexion.commit()
    conexion.close()

    repositorio = SQLiteIncidentRepository(str(ruta))
    columnas = {
        fila["name"] for fila in repositorio.conn.execute("PRAGMA table_info(incidents)")
    }
    indices = {
        fila["name"] for fila in repositorio.conn.execute("PRAGMA index_list(incidents)")
    }

    assert {"recommended_team", "duplicate_group_key"} <= columnas
    assert "idx_incidents_dup_key" in indices
    heredado = repositorio.get_incident("INC-1")
    assert heredado is not None
    assert heredado.recommended_team is None
    assert heredado.duplicate_group_key is None


def test_save_incident_rechaza_el_conflicto_sin_sobrescribir() -> None:
    """FR-008: el `INSERT` estricto impide reemplazar el incidente previo."""
    repositorio = SQLiteIncidentRepository()
    original = _incidente("INC-1")
    repositorio.save_incident(original)

    with pytest.raises(IncidentAlreadyExistsError):
        repositorio.save_incident(
            Incident(
                incident_id="INC-1",
                title="Intento de sobrescritura",
                component="auth-identity",
                severity="P3",
                status="OPEN",
                created_at=REFERENCIA,
                raw_text="Otro texto.",
            )
        )

    assert repositorio.get_incident("INC-1") == original


def test_la_siembra_sintetica_es_idempotente() -> None:
    """La siembra del benchmark reutiliza su sentencia y no duplica filas."""
    repositorio = SQLiteIncidentRepository()

    repositorio.seed_synthetic_incidents(10)
    repositorio.seed_synthetic_incidents(10)

    fila = repositorio.conn.execute("SELECT COUNT(*) AS total FROM incidents").fetchone()
    assert fila["total"] == 10


def test_get_incident_mapea_terminales_y_sus_columnas() -> None:
    """FR-018: la auditoría recupera activos y terminales con su contexto."""
    repositorio = SQLiteIncidentRepository()
    resuelto = Incident(
        incident_id="INC-R",
        title="Resuelto",
        component="auth-identity",
        severity="P1",
        status="RESOLVED",
        created_at=REFERENCIA - timedelta(hours=2),
        resolved_at=REFERENCIA - timedelta(minutes=30),
        raw_text="Cuenta bloqueada.",
        recommended_team="Security-IAM",
        duplicate_group_key="INC-0",
    )
    repositorio.save_incident(resuelto)

    assert repositorio.get_incident("INC-R") == resuelto


@pytest.mark.parametrize(
    "columnas",
    ["severity", "status", "recommended_team", "created_at"],
)
def test_get_incident_rechaza_datos_incoherentes(
    columnas: str,
) -> None:
    """FR-031: severidad, estado, equipo o fecha fuera de catálogo se rechazan."""
    repositorio = SQLiteIncidentRepository()
    repositorio.conn.execute(
        "INSERT INTO incidents (incident_id, title, component, severity, status, "
        "created_at, recommended_team) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "INC-X",
            "Incoherente",
            "payments-gateway",
            "P9" if columnas == "severity" else "P0",
            "INVESTIGATING" if columnas == "status" else "OPEN",
            "2026-11-20T11:00:00+00:00"
            if columnas == "created_at"
            else "2026-11-20T11:00:00",
            "Equipo-Inventado" if columnas == "recommended_team" else None,
        ),
    )
    repositorio.conn.commit()

    with pytest.raises(InvalidIncidentError):
        repositorio.get_incident("INC-X")


def test_rechaza_equipo_fuera_del_catalogo_al_escribir() -> None:
    """El adaptador valida el catálogo cerrado antes de escribir."""
    repositorio = SQLiteIncidentRepository()
    incidente = Incident(
        incident_id="INC-1",
        title="Pagos",
        component="payments-gateway",
        severity="P0",
        status="OPEN",
        created_at=REFERENCIA,
        recommended_team="Equipo-Inventado",  # type: ignore[arg-type]
    )

    with pytest.raises(InvalidIncidentError):
        repositorio.save_incident(incidente)


def test_el_plan_de_la_clave_de_grupo_usa_el_indice_nuevo() -> None:
    """T038: `EXPLAIN QUERY PLAN` menciona `idx_incidents_dup_key`."""
    repositorio = SQLiteIncidentRepository()
    repositorio.seed_synthetic_incidents(500)

    plan = repositorio.query_plan_duplicados("INC-00001")

    assert any("idx_incidents_dup_key" in linea for linea in plan)


def test_el_dominio_ordena_lo_que_el_adaptador_no_ordena() -> None:
    """El adaptador no aplica orden: el dominio lo fija para ambos canales."""
    repositorio = SQLiteIncidentRepository()
    repositorio.save_incident(_incidente("INC-9", severity="P3"))
    repositorio.save_incident(
        _incidente("INC-1", severity="P0", created_at=REFERENCIA - timedelta(minutes=10))
    )

    incidentes = repositorio.list_active_incidents(None)
    resumen = summarize_active_incidents(incidentes, REFERENCIA)

    assert [detalle.incident.incident_id for detalle in resumen.incidents] == [
        "INC-1",
        "INC-9",
    ]
