"""Caso de uso de triaje y errores de entrada de la capa de aplicación."""

from src.domain.triage import TriageResult, classify_impact

MAX_INCIDENT_ID = 64
MAX_RAW_TEXT = 10_000

TRIAGE_ID_VACIO = "TRIAGE_ID_VACIO"
TRIAGE_TEXTO_VACIO = "TRIAGE_TEXTO_VACIO"
TRIAGE_ID_DEMASIADO_LARGO = "TRIAGE_ID_DEMASIADO_LARGO"
TRIAGE_TEXTO_DEMASIADO_LARGO = "TRIAGE_TEXTO_DEMASIADO_LARGO"


class ValidationError(Exception):
    """Entrada inválida para un caso de uso.

    Lleva un código estable para que los adaptadores lo traduzcan a su
    transporte sin reinterpretar la regla.
    """

    def __init__(self, code: str, field: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.field = field
        self.detail = detail


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
            raise ValidationError(
                TRIAGE_ID_VACIO,
                "incident_id",
                "El campo incident_id no puede estar vacío ni contener solo espacios.",
            )
        if len(id_limpio) > MAX_INCIDENT_ID:
            raise ValidationError(
                TRIAGE_ID_DEMASIADO_LARGO,
                "incident_id",
                f"El campo incident_id no puede superar {MAX_INCIDENT_ID} caracteres.",
            )

        texto_limpio = (raw_text or "").strip()
        if not texto_limpio:
            raise ValidationError(
                TRIAGE_TEXTO_VACIO,
                "raw_text",
                "El campo raw_text no puede estar vacío ni contener solo espacios.",
            )
        if len(texto_limpio) > MAX_RAW_TEXT:
            raise ValidationError(
                TRIAGE_TEXTO_DEMASIADO_LARGO,
                "raw_text",
                f"El campo raw_text no puede superar {MAX_RAW_TEXT} caracteres.",
            )
