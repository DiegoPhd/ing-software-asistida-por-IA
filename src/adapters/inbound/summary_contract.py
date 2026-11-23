"""Contrato de transporte compartido por HTTP y CLI para el resumen (D6).

Los nombres y tipos del documento canónico viven en un solo lugar; el CLI no
importa nada del adaptador HTTP y ambos canales serializan el mismo objeto.
"""

import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from src.application.services import SUMMARY_REFERENCIA_INVALIDA, ValidationError
from src.domain.models import ActiveIncidentsSummary

# `YYYY-MM-DDTHH:MM:SS[.ffffff]`: separador `T` obligatorio y sin zona horaria.
# Python 3.10 solo admite 3 o 6 dígitos fraccionarios en `fromisoformat`.
_PATRON_REFERENCIA = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3}|\.\d{6})?$"
)

_MENSAJE_REFERENCIA = (
    "El instante de referencia debe usar el formato "
    "YYYY-MM-DDTHH:MM:SS[.ffffff], con separador 'T' y sin zona horaria."
)


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

    Un espacio en lugar de `T`, una zona horaria o un valor no parseable se
    rechazan con el mismo código estable en ambos canales.
    """
    if valor is None:
        return None

    texto = valor.strip()
    if not _PATRON_REFERENCIA.match(texto):
        raise ValidationError(
            SUMMARY_REFERENCIA_INVALIDA, "reference_time", _MENSAJE_REFERENCIA
        )

    try:
        instante = datetime.fromisoformat(texto)
    except ValueError as exc:
        raise ValidationError(
            SUMMARY_REFERENCIA_INVALIDA, "reference_time", _MENSAJE_REFERENCIA
        ) from exc

    if instante.tzinfo is not None and instante.tzinfo.utcoffset(instante) is not None:
        raise ValidationError(
            SUMMARY_REFERENCIA_INVALIDA, "reference_time", _MENSAJE_REFERENCIA
        )
    return instante


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
