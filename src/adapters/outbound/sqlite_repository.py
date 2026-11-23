"""Adaptador de salida SQLite de incidentes y políticas de SLA.

Cierra la deuda deliberada de la Semana 1: una sola consulta con columnas
explícitas, `INNER JOIN` contra la política vigente e índice compuesto para el
filtro por componente. El adaptador no calcula SLA ni ordena resultados.
"""

import argparse
from datetime import datetime, timedelta
import sqlite3
import threading
import time
from typing import List, Optional, Sequence, Tuple

from src.domain.models import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    Incident,
    IncidentStatus,
    InvalidIncidentError,
    SeverityLevel,
)
from src.domain.sla_calculator import SLA_POLICY_TABLE, summarize_active_incidents

TODOS_LOS_ESTADOS: Tuple[IncidentStatus, ...] = ACTIVE_STATUSES + TERMINAL_STATUSES

COLUMNAS_INCIDENTE = (
    "i.incident_id, i.title, i.component, i.severity, "
    "i.status, i.created_at, i.resolved_at, i.raw_text"
)

SQL_CREAR_POLITICAS = """
CREATE TABLE IF NOT EXISTS sla_policies (
    severity TEXT PRIMARY KEY,
    max_resolution_minutes INTEGER NOT NULL,
    operates_24x7 INTEGER NOT NULL
)
"""

SQL_CREAR_INCIDENTES = """
CREATE TABLE IF NOT EXISTS incidents (
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

SQL_CREAR_INDICE = """
CREATE INDEX IF NOT EXISTS idx_incidents_component_status
    ON incidents (component, status)
"""

SQL_LISTAR_ACTIVOS_BASE = f"""
SELECT {COLUMNAS_INCIDENTE}
FROM incidents AS i
INNER JOIN sla_policies AS p ON p.severity = i.severity
WHERE i.status IN ('OPEN', 'IN_PROGRESS')
"""

# Dos variantes para que el filtro por componente resuelva por el índice
# compuesto: `(? IS NULL OR component = ?)` degrada a `SCAN TABLE`.
SQL_LISTAR_ACTIVOS = SQL_LISTAR_ACTIVOS_BASE + "  AND i.component = ?"
SQL_LISTAR_TODOS_LOS_ACTIVOS = SQL_LISTAR_ACTIVOS_BASE

SQL_OBTENER_INCIDENTE = f"""
SELECT {COLUMNAS_INCIDENTE}
FROM incidents AS i
WHERE i.incident_id = ?
"""

SQL_DUPLICADOS_ABIERTOS = f"""
SELECT {COLUMNAS_INCIDENTE}
FROM incidents AS i
INNER JOIN sla_policies AS p ON p.severity = i.severity
WHERE i.status IN ('OPEN', 'IN_PROGRESS')
  AND i.component = ?
  AND i.incident_id <> ?
"""

SQL_GUARDAR_INCIDENTE = """
INSERT OR REPLACE INTO incidents
    (incident_id, title, component, severity, status, created_at, resolved_at, raw_text)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""

SQL_SEMBRAR_POLITICA = """
INSERT OR REPLACE INTO sla_policies
    (severity, max_resolution_minutes, operates_24x7)
VALUES (?, ?, ?)
"""

COMPONENTES_SINTETICOS = (
    "payments-gateway",
    "auth-identity",
    "database-cluster",
    "reporting-api",
    "frontend-ui",
)
SEVERIDADES_SINTETICAS: Tuple[SeverityLevel, ...] = ("P0", "P1", "P2", "P3")
ESTADOS_SINTETICOS: Tuple[IncidentStatus, ...] = ("OPEN", "IN_PROGRESS")


def _validar_fecha(instante: datetime, campo: str) -> None:
    """Rechaza fechas con zona: el esquema solo admite ISO 8601 naive."""
    if instante.tzinfo is not None and instante.tzinfo.utcoffset(instante) is not None:
        raise InvalidIncidentError(
            f"El campo {campo} debe ser una fecha naive sin zona horaria."
        )


class SQLiteIncidentRepository:
    """Persistencia SQLite del contrato `IncidentRepositoryPort`."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Crea el esquema, migra `raw_text` y siembra las políticas del dominio."""
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(SQL_CREAR_POLITICAS)
            cursor.execute(SQL_CREAR_INCIDENTES)
            cursor.execute(SQL_CREAR_INDICE)
            self._migrar_raw_text(cursor)
            cursor.executemany(
                SQL_SEMBRAR_POLITICA,
                [
                    (
                        regla.severity,
                        regla.max_resolution_minutes,
                        1 if regla.operates_24x7 else 0,
                    )
                    for regla in SLA_POLICY_TABLE.values()
                ],
            )
            self.conn.commit()

    @staticmethod
    def _migrar_raw_text(cursor: sqlite3.Cursor) -> None:
        """Añade `raw_text` a bases heredadas de la Semana 1."""
        columnas = {fila["name"] for fila in cursor.execute("PRAGMA table_info(incidents)")}
        if "raw_text" not in columnas:
            cursor.execute("ALTER TABLE incidents ADD COLUMN raw_text TEXT")

    @staticmethod
    def _validar_incidente(incident: Incident) -> None:
        """Aplica los invariantes del modelo antes de escribir."""
        if not (incident.incident_id or "").strip():
            raise InvalidIncidentError(
                "El campo incident_id no puede estar vacío ni contener solo espacios."
            )
        if not (incident.component or "").strip():
            raise InvalidIncidentError(
                "El campo component no puede estar vacío ni contener solo espacios."
            )
        if incident.severity not in SLA_POLICY_TABLE:
            raise InvalidIncidentError(
                f"Severidad sin política vigente: {incident.severity}"
            )
        if incident.status not in TODOS_LOS_ESTADOS:
            raise InvalidIncidentError(f"Estado de incidente desconocido: {incident.status}")
        _validar_fecha(incident.created_at, "created_at")
        if incident.resolved_at is not None:
            _validar_fecha(incident.resolved_at, "resolved_at")
        if incident.status in TERMINAL_STATUSES and incident.resolved_at is None:
            raise InvalidIncidentError(
                f"El incidente {incident.incident_id} está en estado terminal "
                "y no registra resolved_at."
            )

    @staticmethod
    def _fecha(valor: str, campo: str) -> datetime:
        instante = datetime.fromisoformat(valor)
        _validar_fecha(instante, campo)
        return instante

    @classmethod
    def _fila_a_incidente(cls, fila: sqlite3.Row) -> Incident:
        """Mapea una fila a la entidad de dominio validando la política vigente."""
        severity = fila["severity"]
        if severity not in SLA_POLICY_TABLE:
            raise InvalidIncidentError(
                f"Severidad sin política vigente en la base: {severity}"
            )
        status = fila["status"]
        if status not in TODOS_LOS_ESTADOS:
            raise InvalidIncidentError(f"Estado de incidente desconocido en la base: {status}")
        return Incident(
            incident_id=fila["incident_id"],
            title=fila["title"],
            component=fila["component"],
            severity=severity,
            status=status,
            created_at=cls._fecha(fila["created_at"], "created_at"),
            resolved_at=(
                cls._fecha(fila["resolved_at"], "resolved_at")
                if fila["resolved_at"]
                else None
            ),
            raw_text=fila["raw_text"],
        )

    def save_incident(self, incident: Incident) -> None:
        """Registra o reemplaza un incidente validado."""
        self._validar_incidente(incident)
        with self._lock:
            self.conn.execute(
                SQL_GUARDAR_INCIDENTE,
                (
                    incident.incident_id,
                    incident.title,
                    incident.component,
                    incident.severity,
                    incident.status,
                    incident.created_at.isoformat(),
                    incident.resolved_at.isoformat() if incident.resolved_at else None,
                    incident.raw_text,
                ),
            )
            self.conn.commit()

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Devuelve el incidente con ese identificador, o `None`."""
        with self._lock:
            fila = self.conn.execute(SQL_OBTENER_INCIDENTE, (incident_id,)).fetchone()
        return self._fila_a_incidente(fila) if fila is not None else None

    def find_open_duplicates(self, incident: Incident) -> Sequence[Incident]:
        """Candidatos activos del mismo componente; la similitud es de H003."""
        with self._lock:
            filas = self.conn.execute(
                SQL_DUPLICADOS_ABIERTOS,
                (incident.component, incident.incident_id),
            ).fetchall()
        return [self._fila_a_incidente(fila) for fila in filas]

    def list_active_incidents(
        self, component_filter: Optional[str]
    ) -> Sequence[Incident]:
        """Lista activos con una sola sentencia, sin calcular SLA ni ordenar."""
        if component_filter is None:
            sentencia = SQL_LISTAR_TODOS_LOS_ACTIVOS
            parametros: Tuple[str, ...] = ()
        else:
            sentencia = SQL_LISTAR_ACTIVOS
            parametros = (component_filter,)
        with self._lock:
            filas = self.conn.execute(sentencia, parametros).fetchall()
        return [self._fila_a_incidente(fila) for fila in filas]

    def check_health(self) -> bool:
        """Señal de conectividad (`SELECT 1`)."""
        with self._lock:
            fila = self.conn.execute("SELECT 1").fetchone()
        return fila is not None

    def query_plan(self, component_filter: Optional[str] = None) -> List[str]:
        """Devuelve `EXPLAIN QUERY PLAN` de la consulta del resumen."""
        if component_filter is None:
            sentencia = SQL_LISTAR_TODOS_LOS_ACTIVOS
            parametros: Tuple[str, ...] = ()
        else:
            sentencia = SQL_LISTAR_ACTIVOS
            parametros = (component_filter,)
        with self._lock:
            filas = self.conn.execute(
                f"EXPLAIN QUERY PLAN {sentencia}", parametros
            ).fetchall()
        return [str(fila["detail"]) for fila in filas]

    def seed_synthetic_incidents(self, total_records: int = 10000) -> None:
        """Siembra incidentes activos sintéticos para el benchmark del adaptador."""
        base_time = datetime(2026, 11, 1, 8, 0, 0)
        filas = []
        for indice in range(1, total_records + 1):
            creado = base_time + timedelta(minutes=(indice - 1) % 12000)
            filas.append(
                (
                    f"INC-{indice:05d}",
                    f"Reporte sintético #{indice}",
                    COMPONENTES_SINTETICOS[indice % len(COMPONENTES_SINTETICOS)],
                    SEVERIDADES_SINTETICAS[indice % len(SEVERIDADES_SINTETICAS)],
                    ESTADOS_SINTETICOS[indice % len(ESTADOS_SINTETICOS)],
                    creado.isoformat(),
                    None,
                    None,
                )
            )
        with self._lock:
            self.conn.executemany(SQL_GUARDAR_INCIDENTE, filas)
            self.conn.commit()


def _run_benchmark() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark del adaptador SQLite del resumen de activos"
    )
    parser.add_argument(
        "--records", type=int, default=10000, help="Incidentes activos a sembrar"
    )
    parser.add_argument(
        "--iterations", type=int, default=20, help="Consultas consecutivas a medir"
    )
    args = parser.parse_args()

    if args.iterations < 1:
        parser.error("--iterations debe ser al menos 1")

    repositorio = SQLiteIncidentRepository()
    print(f"Sembrando {args.records} incidentes activos en SQLite en memoria...")
    repositorio.seed_synthetic_incidents(total_records=args.records)

    referencia = datetime(2026, 11, 20, 12, 0, 0)
    componente = "payments-gateway"
    plan = repositorio.query_plan(componente)

    repositorio.list_active_incidents(componente)  # calentamiento
    inicio = time.perf_counter()
    total_activo = 0
    incumplidos = 0
    for _ in range(args.iterations):
        resumen = summarize_active_incidents(
            repositorio.list_active_incidents(componente), referencia
        )
        total_activo = resumen.total_active
        incumplidos = resumen.breached_count
    transcurrido_ms = (time.perf_counter() - inicio) * 1000

    print("=== Resultado del adaptador SQLite (H002) ===")
    print(f"Activos del componente '{componente}': {total_activo}")
    print(f"Incumplidos: {incumplidos}")
    print(f"Tiempo total ({args.iterations} ejecuciones sobre {args.records} filas): {transcurrido_ms:.2f} ms")
    print(f"Promedio por consulta: {transcurrido_ms / args.iterations:.2f} ms")
    print("Plan de consulta (EXPLAIN QUERY PLAN):")
    for linea in plan:
        print(f"  {linea}")


if __name__ == "__main__":
    _run_benchmark()
