"""Adaptador de salida SQLite de incidentes y políticas de SLA.

Cierra la deuda deliberada de la Semana 1: una sola consulta con columnas
explícitas, `INNER JOIN` contra la política vigente e índice compuesto para el
filtro por componente. El adaptador no calcula SLA ni ordena resultados.
"""

import argparse
from datetime import datetime, timedelta
from math import ceil
import sqlite3
import threading
import time
from typing import List, Optional, Sequence, Tuple

from src.adapters.outbound.system_clock import SystemClock
from src.application.services import IncidentAlreadyExistsError, IncidentService
from src.domain.models import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    Incident,
    IncidentStatus,
    InvalidIncidentError,
    SeverityLevel,
)
from src.domain.severity import COMPONENT_TEAM
from src.domain.sla_calculator import SLA_POLICY_TABLE, summarize_active_incidents

TODOS_LOS_ESTADOS: Tuple[IncidentStatus, ...] = ACTIVE_STATUSES + TERMINAL_STATUSES
EQUIPOS_VALIDOS = frozenset(COMPONENT_TEAM.values())

COLUMNAS_INCIDENTE = (
    "i.incident_id, i.title, i.component, i.severity, "
    "i.status, i.created_at, i.resolved_at, i.raw_text, "
    "i.recommended_team, i.duplicate_group_key"
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
    raw_text TEXT,
    recommended_team TEXT,
    duplicate_group_key TEXT
)
"""

SQL_CREAR_INDICE = """
CREATE INDEX IF NOT EXISTS idx_incidents_component_status
    ON incidents (component, status)
"""

SQL_CREAR_INDICE_DUP_KEY = """
CREATE INDEX IF NOT EXISTS idx_incidents_dup_key
    ON incidents (duplicate_group_key, status)
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

SQL_LISTAR_POR_CLAVE_GRUPO = f"""
SELECT {COLUMNAS_INCIDENTE}
FROM incidents AS i
WHERE i.duplicate_group_key = ?
  AND i.status IN ('OPEN', 'IN_PROGRESS')
"""

# El alta usa `INSERT` estricto: un identificador existente es conflicto y
# nunca sobrescribe el incidente previo (FR-008/FR-016).
SQL_GUARDAR_INCIDENTE = """
INSERT INTO incidents
    (incident_id, title, component, severity, status, created_at, resolved_at,
     raw_text, recommended_team, duplicate_group_key)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

# La siembra sintética del benchmark conserva su propia sentencia idempotente;
# no es la ruta de alta.
SQL_SEMBRAR_INCIDENTE = """
INSERT OR REPLACE INTO incidents
    (incident_id, title, component, severity, status, created_at, resolved_at,
     raw_text, recommended_team, duplicate_group_key)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def _texto_temporal(instante: datetime) -> str:
    """Normaliza a `YYYY-MM-DDTHH:MM:SS.ffffff` en ambos motores (FR-009)."""
    return instante.isoformat(timespec="microseconds")


class SQLiteIncidentRepository:
    """Persistencia SQLite del contrato `IncidentRepositoryPort`."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        """Crea el esquema, migra columnas y siembra las políticas del dominio.

        La migración se ejecuta antes de crear `idx_incidents_dup_key` para que
        una base de H002 o de la Semana 1 sin la columna nueva no rompa el
        arranque.
        """
        with self._lock:
            cursor = self.conn.cursor()
            cursor.execute(SQL_CREAR_POLITICAS)
            cursor.execute(SQL_CREAR_INCIDENTES)
            self._migrar_columnas(cursor)
            cursor.execute(SQL_CREAR_INDICE)
            cursor.execute(SQL_CREAR_INDICE_DUP_KEY)
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
    def _migrar_columnas(cursor: sqlite3.Cursor) -> None:
        """Añade de forma idempotente las columnas de H002 y H003 si faltan."""
        columnas = {fila["name"] for fila in cursor.execute("PRAGMA table_info(incidents)")}
        columnas_nuevas = (
            ("raw_text", "TEXT"),
            ("recommended_team", "TEXT"),
            ("duplicate_group_key", "TEXT"),
        )
        for nombre, tipo in columnas_nuevas:
            if nombre not in columnas:
                cursor.execute(f"ALTER TABLE incidents ADD COLUMN {nombre} {tipo}")

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
        if (
            incident.recommended_team is not None
            and incident.recommended_team not in EQUIPOS_VALIDOS
        ):
            raise InvalidIncidentError(
                f"Equipo fuera del catálogo cerrado: {incident.recommended_team}"
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
        recommended_team = fila["recommended_team"]
        if recommended_team is not None and recommended_team not in EQUIPOS_VALIDOS:
            raise InvalidIncidentError(
                f"Equipo fuera del catálogo cerrado en la base: {recommended_team}"
            )
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
            recommended_team=recommended_team,
            duplicate_group_key=fila["duplicate_group_key"],
        )

    def save_incident(self, incident: Incident) -> None:
        """Inserta un incidente validado y rechaza el conflicto de identificador.

        Un `IntegrityError` de la clave primaria se traduce a
        `IncidentAlreadyExistsError`; el incidente previo no se modifica.
        """
        self._validar_incidente(incident)
        with self._lock:
            try:
                self.conn.execute(
                    SQL_GUARDAR_INCIDENTE,
                    (
                        incident.incident_id,
                        incident.title,
                        incident.component,
                        incident.severity,
                        incident.status,
                        _texto_temporal(incident.created_at),
                        _texto_temporal(incident.resolved_at)
                        if incident.resolved_at
                        else None,
                        incident.raw_text,
                        incident.recommended_team,
                        incident.duplicate_group_key,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                self.conn.rollback()
                raise IncidentAlreadyExistsError(incident.incident_id) from exc
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

    def query_plan_duplicados(self, clave: str = "INC-00001") -> List[str]:
        """Devuelve `EXPLAIN QUERY PLAN` de la consulta por clave de grupo."""
        with self._lock:
            filas = self.conn.execute(
                f"EXPLAIN QUERY PLAN {SQL_LISTAR_POR_CLAVE_GRUPO}", (clave,)
            ).fetchall()
        return [str(fila["detail"]) for fila in filas]

    def seed_synthetic_incidents(self, total_records: int = 10000) -> None:
        """Siembra incidentes activos sintéticos para el benchmark del adaptador.

        Cada fila incluye un texto de reporte sintético para que la medición de
        detección de duplicados compare contra candidatos reales. La siembra es
        idempotente y usa su propia sentencia, no la ruta de alta.
        """
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
                    (
                        f"Reporte sintético #{indice}: la pasarela de pagos presenta "
                        "timeouts intermitentes al procesar transacciones con tarjeta."
                    ),
                    None,
                    None,
                )
            )
        with self._lock:
            self.conn.executemany(SQL_SEMBRAR_INCIDENTE, filas)
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

    _medir_alta_y_sla(repositorio, args.iterations)


def _percentil_95(muestras: List[float]) -> float:
    """p95 de una lista de milisegundos ya medida."""
    ordenadas = sorted(muestras)
    indice = max(ceil(0.95 * len(ordenadas)) - 1, 0)
    return ordenadas[indice]


def _medir_alta_y_sla(
    repositorio: SQLiteIncidentRepository, iteraciones: int
) -> None:
    """Registra el p95 del alta y de la auditoría de SLA (SC-006).

    El alta usa un texto de 500 caracteres como máximo, ejecución secuencial y
    los 10.000 activos ya sembrados; la auditoría evalúa un incidente P0
    existente en un instante explícito.
    """
    servicio = IncidentService(repositorio, clock=SystemClock())
    texto = (
        "La pasarela de pagos presenta timeouts intermitentes al procesar "
        "transacciones con tarjeta; varios comercios reportan cobros rechazados."
    )[:500]
    creado = datetime(2026, 11, 20, 13, 0, 0)

    altas: List[float] = []
    for indice in range(iteraciones):
        inicio = time.perf_counter()
        servicio.create_incident(
            f"INC-BENCH-{indice:04d}", texto, created_at=creado
        )
        altas.append((time.perf_counter() - inicio) * 1000)

    auditorias: List[float] = []
    referencia = datetime(2026, 11, 20, 12, 0, 0)
    for _ in range(iteraciones):
        inicio = time.perf_counter()
        servicio.evaluate_incident_sla("INC-00001", reference_time=referencia)
        auditorias.append((time.perf_counter() - inicio) * 1000)

    print("=== Evidencia SC-006 (alta y SLA sobre la misma base) ===")
    print(f"Alta · {iteraciones} ejecuciones · p95: {_percentil_95(altas):.2f} ms")
    print(f"SLA  · {iteraciones} ejecuciones · p95: {_percentil_95(auditorias):.2f} ms")
    print("Plan de consulta por duplicate_group_key/status:")
    for linea in repositorio.query_plan_duplicados():
        print(f"  {linea}")


if __name__ == "__main__":
    _run_benchmark()
