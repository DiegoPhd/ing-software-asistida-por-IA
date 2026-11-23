"""Contrato de transporte compartido por HTTP y CLI para el ciclo de vida (D9).

HTTP lo usa como `response_model` y la CLI serializa el mismo modelo con
`model_dump(mode="json")`, de modo que los documentos coinciden byte a byte sin
que la consola importe el adaptador HTTP. Ningún DTO aplica reglas de negocio:
la clasificación, el título derivado y el SLA vienen del dominio.
"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict

from src.application.services import IncidentCreationResult
from src.domain.models import SLAEvaluationDetail


class CreateIncidentRequest(BaseModel):
    """Cuerpo de `POST /api/v1/incidents` y entrada equivalente por consola."""

    model_config = ConfigDict(extra="forbid")

    incident_id: str
    raw_text: str
    title: Optional[str] = None
    # Se recibe sin tipar para que un tipo incorrecto produzca
    # `CREATE_CREACION_INVALIDA` y no un error genérico de esquema (FR-024).
    created_at: Optional[Any] = None


class IncidentCreatedResponse(BaseModel):
    """Documento canónico de `contracts/incident-created.schema.json`."""

    model_config = ConfigDict(extra="forbid")

    incident_id: str
    title: str
    component: str
    severity: str
    recommended_team: Optional[str]
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]
    duplicate_group_key: Optional[str]
    is_duplicate: bool
    duplicate_of: List[str]


class SLAEvaluationResponse(BaseModel):
    """Documento canónico de `contracts/sla-evaluation.schema.json`."""

    model_config = ConfigDict(extra="forbid")

    incident_id: str
    severity: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]
    reference_time: datetime
    elapsed_minutes: int
    allowed_minutes: int
    remaining_minutes: int
    is_breached: bool
    requires_escalation: bool
    window: str


def to_incident_created_response(
    result: IncidentCreationResult,
) -> IncidentCreatedResponse:
    """Mapea el resultado del alta al documento de transporte."""
    incident = result.incident
    return IncidentCreatedResponse(
        incident_id=incident.incident_id,
        title=incident.title,
        component=incident.component,
        severity=incident.severity,
        recommended_team=incident.recommended_team,
        status=incident.status,
        created_at=incident.created_at,
        resolved_at=incident.resolved_at,
        duplicate_group_key=incident.duplicate_group_key,
        is_duplicate=result.duplicate.is_duplicate,
        duplicate_of=list(result.duplicate.duplicate_of),
    )


def to_sla_evaluation_response(detail: SLAEvaluationDetail) -> SLAEvaluationResponse:
    """Mapea la evaluación con contexto del dominio al documento de transporte."""
    incident = detail.incident
    evaluation = detail.evaluation
    return SLAEvaluationResponse(
        incident_id=incident.incident_id,
        severity=incident.severity,
        status=incident.status,
        created_at=incident.created_at,
        resolved_at=incident.resolved_at,
        reference_time=detail.reference_time,
        elapsed_minutes=evaluation.elapsed_minutes,
        allowed_minutes=evaluation.allowed_minutes,
        remaining_minutes=evaluation.remaining_minutes,
        is_breached=evaluation.is_breached,
        requires_escalation=evaluation.requires_escalation,
        window=detail.window,
    )
