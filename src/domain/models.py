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
    "SEVERITY_INDEX",
    "SLAEvaluation",
    "SLARule",
    "SeverityLevel",
    "TERMINAL_STATUSES",
    "Team",
    "TemporalInconsistencyError",
]

IncidentStatus = Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]

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
