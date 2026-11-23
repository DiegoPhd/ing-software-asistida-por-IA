"""Adaptador de salida PostgreSQL de incidentes y políticas de SLA (ADR-004).

Implementa el mismo `IncidentRepositoryPort` que SQLite con `psycopg` y
`dict_row`: conexión de corta duración por operación, DDL idempotente, siembra
de políticas con `ON CONFLICT DO UPDATE` y `INSERT` estricto en el alta. No
importa el adaptador SQLite, no calcula SLA ni similitud, no resuelve claves de
grupo y no ordena resultados: esas reglas viven en el dominio.

El constructor no exige un servidor vivo: si la base no responde deja el
esquema pendiente y cada operación de negocio lo reintenta bajo un cerrojo. La
comprobación de salud solo ejecuta `SELECT 1`, nunca DDL.
"""

from datetime import datetime
import threading
from typing import List, Optional, Sequence, Tuple

import psycopg
from psycopg.rows import dict_row

from src.application.services import IncidentAlreadyExistsError
from src.domain.models import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    Incident,
    IncidentStatus,
    InvalidIncidentError,
)
from src.domain.severity import COMPONENT_TEAM
from src.domain.sla_calculator import SLA_POLICY_TABLE

TODOS_LOS_ESTADOS: Tuple[IncidentStatus, ...] = ACTIVE_STATUSES + TERMINAL_STATUSES
EQUIPOS_VALIDOS = frozenset(COMPONENT_TEAM.values())

TIEMPO_DE_CONEXION_SEGUNDOS = 2
TIEMPO_DE_COMPROBACION_SEGUNDOS = 2.0
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

# Siembra idempotente de referencia: nunca toca `incidents` (ADR-004 §3e).
SQL_SEMBRAR_POLITICA = """
INSERT INTO sla_policies (severity, max_resolution_minutes, operates_24x7)
VALUES (%s, %s, %s)
ON CONFLICT (severity) DO UPDATE SET
    max_resolution_minutes = EXCLUDED.max_resolution_minutes,
    operates_24x7 = EXCLUDED.operates_24x7
"""

SQL_LISTAR_ACTIVOS_BASE = f"""
SELECT {COLUMNAS_INCIDENTE}
FROM incidents AS i
INNER JOIN sla_policies AS p ON p.severity = i.severity
WHERE i.status IN ('OPEN', 'IN_PROGRESS')
"""

# Dos variantes para que el filtro por componente use el índice compuesto.
SQL_LISTAR_ACTIVOS = SQL_LISTAR_ACTIVOS_BASE + "  AND i.component = %s"
SQL_LISTAR_TODOS_LOS_ACTIVOS = SQL_LISTAR_ACTIVOS_BASE

SQL_OBTENER_INCIDENTE = f"""
SELECT {COLUMNAS_INCIDENTE}
FROM incidents AS i
WHERE i.incident_id = %s
"""

SQL_DUPLICADOS_ABIERTOS = f"""
SELECT {COLUMNAS_INCIDENTE}
FROM incidents AS i
INNER JOIN sla_policies AS p ON p.severity = i.severity
WHERE i.status IN ('OPEN', 'IN_PROGRESS')
  AND i.component = %s
  AND i.incident_id <> %s
"""

# Alta estricta: un identificador existente es conflicto y nunca sobrescribe.
SQL_GUARDAR_INCIDENTE = """
INSERT INTO incidents
    (incident_id, title, component, severity, status, created_at, resolved_at,
     raw_text, recommended_team, duplicate_group_key)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def _validar_fecha(instante: datetime, campo: str) -> None:
    """Rechaza fechas con zona: el esquema solo admite ISO 8601 naive."""
    if instante.tzinfo is not None and instante.tzinfo.utcoffset(instante) is not None:
        raise InvalidIncidentError(
            f"El campo {campo} debe ser una fecha naive sin zona horaria."
        )


def _texto_temporal(instante: datetime) -> str:
    """Normaliza a `YYYY-MM-DDTHH:MM:SS.ffffff` (FR-009)."""
    return instante.isoformat(timespec="microseconds")


class PostgresIncidentRepository:
    """Persistencia PostgreSQL del contrato `IncidentRepositoryPort`."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._schema_lock = threading.Lock()
        self._schema_ready = False
        try:
            self._ensure_schema()
        except (psycopg.Error, OSError):
            # Arranque tolerante: el esquema se reintenta en la primera operación.
            self._schema_ready = False

    # ------------------------------------------------------------------
    # Conexión y esquema
    # ------------------------------------------------------------------

    def _connect(self) -> "psycopg.Connection":
        """Abre una conexión corta con espera acotada y filas por nombre."""
        return psycopg.connect(
            self._dsn,
            row_factory=dict_row,
            connect_timeout=TIEMPO_DE_CONEXION_SEGUNDOS,
        )

    def _ensure_schema(self) -> None:
        """Crea tablas, índices y políticas de forma idempotente."""
        if self._schema_ready:
            return
        with self._schema_lock:
            if self._schema_ready:
                return
            with self._connect() as conexion:
                with conexion.cursor() as cursor:
                    cursor.execute(SQL_CREAR_POLITICAS)
                    cursor.execute(SQL_CREAR_INCIDENTES)
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
            self._schema_ready = True

    # ------------------------------------------------------------------
    # Validación y mapeo (replicados deliberadamente, sin importar SQLite)
    # ------------------------------------------------------------------

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
    def _fila_a_incidente(cls, fila: dict) -> Incident:
        """Mapea una fila `dict_row` a la entidad de dominio validando catálogos."""
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

    # ------------------------------------------------------------------
    # Puerto
    # ------------------------------------------------------------------

    def save_incident(self, incident: Incident) -> None:
        """Inserta un incidente validado y rechaza el conflicto de identificador.

        La violación de unicidad (`UniqueViolation`, sqlstate 23505) se traduce
        a `IncidentAlreadyExistsError`; la fila previa no se modifica.
        """
        self._validar_incidente(incident)
        self._ensure_schema()
        parametros = (
            incident.incident_id,
            incident.title,
            incident.component,
            incident.severity,
            incident.status,
            _texto_temporal(incident.created_at),
            _texto_temporal(incident.resolved_at) if incident.resolved_at else None,
            incident.raw_text,
            incident.recommended_team,
            incident.duplicate_group_key,
        )
        try:
            with self._connect() as conexion:
                with conexion.cursor() as cursor:
                    cursor.execute(SQL_GUARDAR_INCIDENTE, parametros)
        except psycopg.errors.UniqueViolation as exc:
            raise IncidentAlreadyExistsError(incident.incident_id) from exc

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Devuelve el incidente con ese identificador, o `None`."""
        self._ensure_schema()
        with self._connect() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(SQL_OBTENER_INCIDENTE, (incident_id,))
                fila = cursor.fetchone()
        return self._fila_a_incidente(fila) if fila is not None else None

    def find_open_duplicates(self, incident: Incident) -> Sequence[Incident]:
        """Candidatos activos del mismo componente; la similitud es de H003."""
        self._ensure_schema()
        with self._connect() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(
                    SQL_DUPLICADOS_ABIERTOS,
                    (incident.component, incident.incident_id),
                )
                filas = cursor.fetchall()
        return [self._fila_a_incidente(fila) for fila in filas]

    def list_active_incidents(
        self, component_filter: Optional[str]
    ) -> Sequence[Incident]:
        """Lista activos con una sola sentencia, sin calcular SLA ni ordenar."""
        self._ensure_schema()
        if component_filter is None:
            sentencia = SQL_LISTAR_TODOS_LOS_ACTIVOS
            parametros: Tuple[str, ...] = ()
        else:
            sentencia = SQL_LISTAR_ACTIVOS
            parametros = (component_filter,)
        with self._connect() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute(sentencia, parametros)
                filas = cursor.fetchall()
        return [self._fila_a_incidente(fila) for fila in filas]

    def check_health(self) -> bool:
        """Conectividad real (`SELECT 1`) acotada, sin DDL y sin lanzar.

        La espera se aplica con un hilo de trabajo porque libpq no acota la
        resolución DNS: un nombre de contenedor detenido tarda ~4 s en fallar y
        `connect_timeout` no cubre ese tramo. Si el resultado no llega dentro
        del plazo, la comprobación informa `False` (RNF-002).
        """
        resultado: List[bool] = []

        def _consultar() -> None:
            try:
                with self._connect() as conexion:
                    with conexion.cursor() as cursor:
                        cursor.execute("SELECT 1")
                        resultado.append(cursor.fetchone() is not None)
            except Exception:
                # El contrato del puerto exige no lanzar nunca: cualquier fallo
                # de conexión, autenticación o tiempo se informa como caída.
                resultado.append(False)

        hilo = threading.Thread(
            target=_consultar, name="incidentops-health", daemon=True
        )
        hilo.start()
        hilo.join(TIEMPO_DE_COMPROBACION_SEGUNDOS)
        return bool(resultado and resultado[0])
