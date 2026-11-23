"""Casos de uso de triaje y resumen de incidentes activos.

La aplicación solo orquesta: valida la entrada, llama al puerto y delega el
cálculo de SLA, el orden y los totales en `src.domain.sla_calculator`.
"""

from datetime import datetime
from typing import Optional

from src.application.ports import IncidentRepositoryPort
from src.domain.models import ActiveIncidentsSummary, TemporalInconsistencyError
from src.domain.sla_calculator import summarize_active_incidents
from src.domain.triage import TriageResult, classify_impact

MAX_INCIDENT_ID = 64
MAX_RAW_TEXT = 10_000
MAX_COMPONENT = 128

TRIAGE_ID_VACIO = "TRIAGE_ID_VACIO"
TRIAGE_TEXTO_VACIO = "TRIAGE_TEXTO_VACIO"
TRIAGE_ID_DEMASIADO_LARGO = "TRIAGE_ID_DEMASIADO_LARGO"
TRIAGE_TEXTO_DEMASIADO_LARGO = "TRIAGE_TEXTO_DEMASIADO_LARGO"

SUMMARY_COMPONENTE_DEMASIADO_LARGO = "SUMMARY_COMPONENTE_DEMASIADO_LARGO"
SUMMARY_REFERENCIA_INVALIDA = "SUMMARY_REFERENCIA_INVALIDA"
SUMMARY_SOLICITUD_INVALIDA = "SUMMARY_SOLICITUD_INVALIDA"
SUMMARY_REFERENCIA_INCONSISTENTE = "SUMMARY_REFERENCIA_INCONSISTENTE"
SUMMARY_ERROR_INTERNO = "SUMMARY_ERROR_INTERNO"


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


class DataInconsistencyError(Exception):
    """Dato almacenado incoherente con la consulta.

    Se distingue de `ValidationError` porque el cliente no puede corregir el
    dato: el adaptador lo traduce a 409 (HTTP) o al código de salida 1 (CLI).
    """

    def __init__(self, code: str, field: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.field = field
        self.detail = detail


class IncidentService:
    """Orquesta el triaje de un reporte y el resumen de incidentes activos."""

    def __init__(self, repository: IncidentRepositoryPort) -> None:
        self._repository = repository

    def triage_incident(self, incident_id: str, raw_text: str) -> TriageResult:
        """Valida la entrada y delega la clasificación en el dominio."""
        self._validar(incident_id, raw_text)
        return classify_impact(incident_id, raw_text)

    def get_active_incidents_summary(
        self,
        reference_time: Optional[datetime] = None,
        component_filter: Optional[str] = None,
    ) -> ActiveIncidentsSummary:
        """Consulta los activos y delega totales y orden en el dominio.

        Si `reference_time` se omite, el instante actual se resuelve una sola vez
        y se aplica a todos los incidentes de la respuesta (FR-014).
        """
        filtro = self._normalizar_componente(component_filter)
        instante = reference_time if reference_time is not None else datetime.now()
        if instante.tzinfo is not None and instante.tzinfo.utcoffset(instante) is not None:
            raise ValidationError(
                SUMMARY_REFERENCIA_INVALIDA,
                "reference_time",
                "El instante de referencia debe ser una fecha naive sin zona horaria.",
            )

        incidentes = self._repository.list_active_incidents(filtro)
        try:
            return summarize_active_incidents(incidentes, instante)
        except TemporalInconsistencyError as exc:
            raise DataInconsistencyError(
                SUMMARY_REFERENCIA_INCONSISTENTE,
                "reference_time",
                str(exc),
            ) from exc

    @staticmethod
    def _normalizar_componente(component_filter: Optional[str]) -> Optional[str]:
        """Recorta espacios, convierte vacío en `None` y limita a 128 caracteres."""
        limpio = (component_filter or "").strip()
        if not limpio:
            return None
        if len(limpio) > MAX_COMPONENT:
            raise ValidationError(
                SUMMARY_COMPONENTE_DEMASIADO_LARGO,
                "component",
                f"El campo component no puede superar {MAX_COMPONENT} caracteres.",
            )
        return limpio

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
