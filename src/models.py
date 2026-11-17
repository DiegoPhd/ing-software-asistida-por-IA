from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal

SeverityLevel = Literal["P0", "P1", "P2", "P3"]
IncidentStatus = Literal["OPEN", "RESOLVED", "INVESTIGATING"]

@dataclass(frozen=True)
class SLARule:
    """Define el acuerdo de nivel de servicio (SLA) para un nivel de severidad."""
    severity: SeverityLevel
    max_resolution_minutes: int
    operates_24x7: bool
    escalation_threshold_ratio: float = 0.75

@dataclass
class Incident:
    """Representa un incidente registrado en la plataforma IncidentOps."""
    incident_id: str
    title: str
    component: str
    severity: SeverityLevel
    status: IncidentStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None
    raw_text: Optional[str] = None

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
class TriageResult:
    """Resultado estructurado producido por el clasificador de triaje con impacto real."""
    incident_id: str
    severity: SeverityLevel
    component: str
    recommended_team: str
    rationale: str
    duplicate_group_key: Optional[str] = None
    consistency_ratio: float = 1.0