"""Caso de uso de triaje compartido por los adaptadores de entrada."""

from src.application.errors import (
    MAX_INCIDENT_ID,
    MAX_RAW_TEXT,
    TRIAGE_ID_DEMASIADO_LARGO,
    TRIAGE_ID_VACIO,
    TRIAGE_TEXTO_DEMASIADO_LARGO,
    TRIAGE_TEXTO_VACIO,
    TriageValidationError,
)
from src.domain.triage import TriageResult, classify_impact


class IncidentService:
    """Orquesta el triaje de un reporte individual.

    En H001 no declara puertos de salida: la clasificación es pura y no
    depende de reloj, repositorio ni política externa.
    """

    def triage_incident(self, incident_id: str, raw_text: str) -> TriageResult:
        """Valida la entrada y delega la clasificación en el dominio."""
        self._validar(incident_id, raw_text)
        return classify_impact(incident_id, raw_text)

    @staticmethod
    def _validar(incident_id: str, raw_text: str) -> None:
        id_limpio = (incident_id or "").strip()
        if not id_limpio:
            raise TriageValidationError(
                TRIAGE_ID_VACIO,
                "incident_id",
                "El campo incident_id no puede estar vacío ni contener solo espacios.",
            )
        if len(id_limpio) > MAX_INCIDENT_ID:
            raise TriageValidationError(
                TRIAGE_ID_DEMASIADO_LARGO,
                "incident_id",
                f"El campo incident_id no puede superar {MAX_INCIDENT_ID} caracteres.",
            )

        texto_limpio = (raw_text or "").strip()
        if not texto_limpio:
            raise TriageValidationError(
                TRIAGE_TEXTO_VACIO,
                "raw_text",
                "El campo raw_text no puede estar vacío ni contener solo espacios.",
            )
        if len(texto_limpio) > MAX_RAW_TEXT:
            raise TriageValidationError(
                TRIAGE_TEXTO_DEMASIADO_LARGO,
                "raw_text",
                f"El campo raw_text no puede superar {MAX_RAW_TEXT} caracteres.",
            )
