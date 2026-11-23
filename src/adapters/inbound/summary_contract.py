"""Contrato de transporte compartido por HTTP y CLI para el resumen (D6).

Los nombres y tipos del documento canónico viven en un solo lugar; el CLI no
importa nada del adaptador HTTP y ambos canales serializan el mismo objeto.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from src.adapters.inbound.temporal_contract import parse_instante_naive
from src.application.services import SUMMARY_REFERENCIA_INVALIDA
from src.domain.models import ActiveIncidentsSummary


class ActiveIncidentItem(BaseModel):
    """Entrada de detalle del resumen, mapeada desde el dominio."""

    incident_id: str
    title: str
    component: str
    severity: str
    status: str
    elapsed_minutes: int
    is_breached: bool
    requires_escalation: bool


class ActiveIncidentsSummaryResponse(BaseModel):
    """Documento canónico de `contracts/summary.schema.json`."""

    total_active: int
    breached_count: int
    incidents: List[ActiveIncidentItem]


def parse_reference_time(valor: Optional[str]) -> Optional[datetime]:
    """Valida el instante de referencia ISO 8601 naive, o devuelve `None`.

    Delega en el parser temporal compartido conservando el código estable
    `SUMMARY_REFERENCIA_INVALIDA` y su comportamiento de H002.
    """
    return parse_instante_naive(valor, "reference_time", SUMMARY_REFERENCIA_INVALIDA)


def to_summary_response(summary: ActiveIncidentsSummary) -> ActiveIncidentsSummaryResponse:
    """Mapea el resultado del dominio al documento de transporte."""
    return ActiveIncidentsSummaryResponse(
        total_active=summary.total_active,
        breached_count=summary.breached_count,
        incidents=[
            ActiveIncidentItem(
                incident_id=detalle.incident.incident_id,
                title=detalle.incident.title,
                component=detalle.incident.component,
                severity=detalle.incident.severity,
                status=detalle.incident.status,
                elapsed_minutes=detalle.evaluation.elapsed_minutes,
                is_breached=detalle.evaluation.is_breached,
                requires_escalation=detalle.evaluation.requires_escalation,
            )
            for detalle in summary.incidents
        ],
    )
