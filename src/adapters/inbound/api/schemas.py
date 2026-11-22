"""DTOs de transporte del adaptador REST.

Los esquemas se mapean explícitamente desde y hacia el dominio; no contienen
reglas de negocio ni reutilizan los tipos del núcleo como contrato HTTP.
"""

from typing import Optional

from pydantic import BaseModel


class TriageRequest(BaseModel):
    """Cuerpo de la petición de triaje de un reporte."""

    incident_id: str
    raw_text: str


class TriageResponse(BaseModel):
    """Representación de transporte del resultado de triaje."""

    incident_id: str
    severity: str
    component: str
    recommended_team: str
    rationale: str
    duplicate_group_key: Optional[str] = None
