"""Errores de caso de uso y límites de entrada del triaje."""

MAX_INCIDENT_ID = 64
MAX_RAW_TEXT = 10_000

TRIAGE_ID_VACIO = "TRIAGE_ID_VACIO"
TRIAGE_TEXTO_VACIO = "TRIAGE_TEXTO_VACIO"
TRIAGE_ID_DEMASIADO_LARGO = "TRIAGE_ID_DEMASIADO_LARGO"
TRIAGE_TEXTO_DEMASIADO_LARGO = "TRIAGE_TEXTO_DEMASIADO_LARGO"


class TriageValidationError(Exception):
    """Entrada inválida para un caso de uso de triaje.

    Lleva un código estable para que los adaptadores lo traduzcan a su
    transporte sin reinterpretar la regla.
    """

    def __init__(self, code: str, field: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.field = field
        self.detail = detail
