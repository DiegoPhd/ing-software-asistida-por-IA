"""Entidades, estados y errores del núcleo de IncidentOps (Constitución §I).

El dominio no conoce frameworks, persistencia ni reloj: estas estructuras son
inmutables y `src/domain/sla_calculator.py` es el único módulo que las evalúa.
"""

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Literal, Mapping, Optional, Tuple

from src.domain.severity import SeverityLevel, Team

__all__ = [
    "ACTIVE_STATUSES",
    "ActiveIncidentDetail",
    "ActiveIncidentsSummary",
    "DomainError",
    "Incident",
    "IncidentStatus",
    "InvalidIncidentError",
    "MAX_TITULO",
    "SEVERITY_INDEX",
    "SLAComputationWindow",
    "SLAEvaluation",
    "SLAEvaluationDetail",
    "SLARule",
    "SeverityLevel",
    "TERMINAL_STATUSES",
    "Team",
    "TemporalInconsistencyError",
    "derivar_titulo",
]

IncidentStatus = Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]

SLAComputationWindow = Literal["24x7", "BUSINESS_HOURS"]

MAX_TITULO = 200

ACTIVE_STATUSES: Tuple[IncidentStatus, ...] = ("OPEN", "IN_PROGRESS")
TERMINAL_STATUSES: Tuple[IncidentStatus, ...] = ("RESOLVED", "CLOSED")

SEVERITY_INDEX: Mapping[SeverityLevel, int] = MappingProxyType(
    {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
)


class DomainError(ValueError):
    """Error de una regla de negocio del núcleo."""


class InvalidIncidentError(DomainError):
    """Dato de incidente que viola los invariantes del dominio."""


class TemporalInconsistencyError(DomainError):
    """El instante de referencia es incoherente con las fechas del incidente."""


@dataclass(frozen=True)
class SLARule:
    """Acuerdo de nivel de servicio vigente para una severidad."""

    severity: SeverityLevel
    max_resolution_minutes: int
    operates_24x7: bool
    escalation_threshold_ratio: float = 0.75


@dataclass(frozen=True)
class Incident:
    """Incidente registrado en la plataforma IncidentOps."""

    incident_id: str
    title: str
    component: str
    severity: SeverityLevel
    status: IncidentStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None
    raw_text: Optional[str] = None
    recommended_team: Optional[Team] = None
    duplicate_group_key: Optional[str] = None


@dataclass(frozen=True)
class SLAEvaluation:
    """Resultado determinista de la evaluación de SLA de un incidente."""

    incident_id: str
    severity: SeverityLevel
    elapsed_minutes: int
    allowed_minutes: int
    remaining_minutes: int
    is_breached: bool
    requires_escalation: bool


@dataclass(frozen=True)
class SLAEvaluationDetail:
    """Auditoría de SLA con su contexto temporal y su ventana de cómputo."""

    incident: Incident
    evaluation: SLAEvaluation
    reference_time: datetime
    window: SLAComputationWindow


@dataclass(frozen=True)
class ActiveIncidentDetail:
    """Incidente activo junto con su evaluación de SLA."""

    incident: Incident
    evaluation: SLAEvaluation


@dataclass(frozen=True)
class ActiveIncidentsSummary:
    """Totales y detalle ordenado del conjunto de incidentes activos."""

    total_active: int
    breached_count: int
    incidents: Tuple[ActiveIncidentDetail, ...]


def derivar_titulo(raw_text: str) -> str:
    """Deriva el título de un reporte: primera línea recortada, máximo 200.

    Es determinista y no depende de reloj ni de estado: la primera línea no
    vacía del texto recortado actúa como título y, si el reporte empieza con
    líneas en blanco, se usa el texto completo recortado. El resultado nunca
    supera `MAX_TITULO` caracteres.
    """
    texto = (raw_text or "").strip()
    if not texto:
        return ""
    primera_linea = texto.splitlines()[0].strip()
    base = primera_linea or texto
    return base[:MAX_TITULO]
