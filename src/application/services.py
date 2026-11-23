"""Casos de uso de triaje, alta persistente, resumen y auditoría de SLA.

La aplicación solo orquesta: valida la entrada, serializa por componente, llama
al puerto y delega las reglas (clasificación, equivalencia y SLA) en
`src.domain`. No conoce frameworks, SQL ni el reloj concreto.
"""

from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
import threading
from typing import Dict, Iterator, Optional

from src.application.ports import ClockPort, IncidentRepositoryPort
from src.domain.models import (
    MAX_TITULO,
    ActiveIncidentsSummary,
    Incident,
    InvalidIncidentError,
    SLAEvaluationDetail,
    TemporalInconsistencyError,
    derivar_titulo,
)
from src.domain.sla_calculator import evaluate_sla_detail, summarize_active_incidents
from src.domain.triage_rules import (
    DuplicateAssessment,
    TriageResult,
    assess_duplicates,
    classify_impact,
)

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

CREATE_ID_VACIO = "CREATE_ID_VACIO"
CREATE_ID_DEMASIADO_LARGO = "CREATE_ID_DEMASIADO_LARGO"
CREATE_TEXTO_VACIO = "CREATE_TEXTO_VACIO"
CREATE_TEXTO_DEMASIADO_LARGO = "CREATE_TEXTO_DEMASIADO_LARGO"
CREATE_TITULO_VACIO = "CREATE_TITULO_VACIO"
CREATE_TITULO_DEMASIADO_LARGO = "CREATE_TITULO_DEMASIADO_LARGO"
CREATE_CREACION_INVALIDA = "CREATE_CREACION_INVALIDA"
CREATE_SOLICITUD_INVALIDA = "CREATE_SOLICITUD_INVALIDA"
CREATE_ID_CONFLICTO = "CREATE_ID_CONFLICTO"
CREATE_ERROR_INTERNO = "CREATE_ERROR_INTERNO"

SLA_ID_VACIO = "SLA_ID_VACIO"
SLA_REFERENCIA_INVALIDA = "SLA_REFERENCIA_INVALIDA"
SLA_SOLICITUD_INVALIDA = "SLA_SOLICITUD_INVALIDA"
SLA_REFERENCIA_INCONSISTENTE = "SLA_REFERENCIA_INCONSISTENTE"
SLA_DATOS_INCONSISTENTES = "SLA_DATOS_INCONSISTENTES"
SLA_INCIDENTE_NO_ENCONTRADO = "SLA_INCIDENTE_NO_ENCONTRADO"
SLA_ERROR_INTERNO = "SLA_ERROR_INTERNO"


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
    dato: el adaptador lo traduce al estado HTTP indicado por `status` y al
    código de salida 1 de la CLI. El resumen de H002 conserva su 409; la
    auditoría usa 422 para una referencia incoherente y 409 para el dato.
    """

    def __init__(self, code: str, field: str, detail: str, status: int = 409) -> None:
        super().__init__(detail)
        self.code = code
        self.field = field
        self.detail = detail
        self.status = status


class IncidentAlreadyExistsError(Exception):
    """El identificador ya corresponde a un incidente almacenado (FR-008)."""

    def __init__(self, incident_id: str, detail: Optional[str] = None) -> None:
        self.code = CREATE_ID_CONFLICTO
        self.field = "incident_id"
        self.detail = detail or (
            f"El identificador {incident_id} ya corresponde a un incidente almacenado."
        )
        super().__init__(self.detail)


class IncidentNotFoundError(Exception):
    """El identificador consultado no existe en el almacenamiento (FR-023)."""

    def __init__(self, incident_id: str, detail: Optional[str] = None) -> None:
        self.code = SLA_INCIDENTE_NO_ENCONTRADO
        self.field = "incident_id"
        self.detail = detail or (
            f"No existe un incidente con el identificador {incident_id}."
        )
        super().__init__(self.detail)


@dataclass(frozen=True)
class IncidentCreationResult:
    """Incidente persistido junto con el veredicto informativo de duplicados."""

    incident: Incident
    duplicate: DuplicateAssessment


class IncidentService:
    """Orquesta triaje, alta, resumen y auditoría de SLA de incidentes."""

    def __init__(
        self, repository: IncidentRepositoryPort, clock: Optional[ClockPort] = None
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._locks_guard = threading.Lock()
        self._component_locks: Dict[str, threading.Lock] = {}

    # ------------------------------------------------------------------
    # H004 · Salud del servicio
    # ------------------------------------------------------------------

    def check_health(self) -> bool:
        """Delega la conectividad en el puerto sin capturar excepciones.

        El adaptador es responsable de no lanzar y de devolver `False` ante
        cualquier fallo; capturar aquí ocultaría un adaptador que incumple el
        puerto (FR-004/FR-005).
        """
        return self._repository.check_health()

    # ------------------------------------------------------------------
    # Casos de uso de H001 y H002
    # ------------------------------------------------------------------

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
        instante = reference_time if reference_time is not None else self._ahora()
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

    # ------------------------------------------------------------------
    # H003 · Alta persistente con aviso de duplicados
    # ------------------------------------------------------------------

    def create_incident(
        self,
        incident_id: str,
        raw_text: str,
        title: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> IncidentCreationResult:
        """Clasifica, detecta duplicados previos y persiste un incidente en OPEN.

        El texto original se conserva sin normalizar; solo se recorta para
        validar. El título se deriva del texto cuando se omite. La detección y
        la escritura se serializan por componente con un cerrojo de proceso: la
        garantía no cubre dos procesos ni réplicas (FR-030, ADR-006).
        """
        id_limpio = self._validar_identificador_de_alta(incident_id)
        texto = raw_text or ""
        if not texto.strip():
            raise ValidationError(
                CREATE_TEXTO_VACIO,
                "raw_text",
                "El campo raw_text no puede estar vacío ni contener solo espacios.",
            )
        if len(texto.strip()) > MAX_RAW_TEXT:
            raise ValidationError(
                CREATE_TEXTO_DEMASIADO_LARGO,
                "raw_text",
                f"El campo raw_text no puede superar {MAX_RAW_TEXT} caracteres.",
            )

        titulo = self._resolver_titulo(title, texto)
        instante = created_at if created_at is not None else self._ahora()
        self._validar_creacion(instante)

        triaje = classify_impact(id_limpio, texto)
        incidente = Incident(
            incident_id=id_limpio,
            title=titulo,
            component=triaje.component,
            severity=triaje.severity,
            status="OPEN",
            created_at=instante,
            resolved_at=None,
            raw_text=texto,
            recommended_team=triaje.recommended_team,
            duplicate_group_key=None,
        )

        with self._cerrojo_de_componente(triaje.component):
            candidatos = self._repository.find_open_duplicates(incidente)
            evaluacion = assess_duplicates(incidente, candidatos)
            if evaluacion.duplicate_group_key is not None:
                incidente = replace(
                    incidente, duplicate_group_key=evaluacion.duplicate_group_key
                )
            # El puerto traduce el conflicto de clave primaria; nunca reemplaza.
            self._repository.save_incident(incidente)

        return IncidentCreationResult(incident=incidente, duplicate=evaluacion)

    # ------------------------------------------------------------------
    # H003 · Auditoría de SLA de un incidente concreto
    # ------------------------------------------------------------------

    def evaluate_incident_sla(
        self, incident_id: str, reference_time: Optional[datetime] = None
    ) -> SLAEvaluationDetail:
        """Evalúa el SLA de un incidente almacenado sin modificar ningún dato.

        Resuelve el instante una sola vez, traduce la ausencia del incidente a
        `IncidentNotFoundError` y distingue la referencia incoherente (422) de
        un dato almacenado incoherente (409).
        """
        id_limpio = (incident_id or "").strip()
        if not id_limpio:
            raise ValidationError(
                SLA_ID_VACIO,
                "incident_id",
                "El campo incident_id no puede estar vacío ni contener solo espacios.",
            )

        instante = reference_time if reference_time is not None else self._ahora()
        if not isinstance(instante, datetime) or (
            instante.tzinfo is not None and instante.tzinfo.utcoffset(instante) is not None
        ):
            raise ValidationError(
                SLA_REFERENCIA_INVALIDA,
                "reference_time",
                "El instante de referencia debe ser una fecha naive sin zona horaria.",
            )

        try:
            incidente = self._repository.get_incident(id_limpio)
        except InvalidIncidentError as exc:
            raise DataInconsistencyError(
                SLA_DATOS_INCONSISTENTES,
                "incident_id",
                str(exc),
                status=409,
            ) from exc

        if incidente is None:
            raise IncidentNotFoundError(id_limpio)

        try:
            return evaluate_sla_detail(incidente, instante)
        except TemporalInconsistencyError as exc:
            raise DataInconsistencyError(
                SLA_REFERENCIA_INCONSISTENTE,
                "reference_time",
                str(exc),
                status=422,
            ) from exc
        except InvalidIncidentError as exc:
            raise DataInconsistencyError(
                SLA_DATOS_INCONSISTENTES,
                "incident_id",
                str(exc),
                status=409,
            ) from exc

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    def _ahora(self) -> datetime:
        """Resuelve el instante actual con el reloj inyectado o el heredado."""
        if self._clock is not None:
            return self._clock.now()
        return datetime.now()

    @contextmanager
    def _cerrojo_de_componente(self, component: str) -> Iterator[None]:
        """Serializa detección y escritura por componente dentro del proceso.

        El registro crece con el catálogo cerrado de componentes, no con el
        volumen de incidentes. No hay bloqueo distribuido entre procesos.
        """
        with self._locks_guard:
            cerrojo = self._component_locks.setdefault(component, threading.Lock())
        with cerrojo:
            yield

    @staticmethod
    def _validar_identificador_de_alta(incident_id: str) -> str:
        id_limpio = (incident_id or "").strip()
        if not id_limpio:
            raise ValidationError(
                CREATE_ID_VACIO,
                "incident_id",
                "El campo incident_id no puede estar vacío ni contener solo espacios.",
            )
        if len(id_limpio) > MAX_INCIDENT_ID:
            raise ValidationError(
                CREATE_ID_DEMASIADO_LARGO,
                "incident_id",
                f"El campo incident_id no puede superar {MAX_INCIDENT_ID} caracteres.",
            )
        return id_limpio

    @staticmethod
    def _resolver_titulo(title: Optional[str], raw_text: str) -> str:
        if title is None:
            return derivar_titulo(raw_text)
        titulo = title.strip()
        if not titulo:
            raise ValidationError(
                CREATE_TITULO_VACIO,
                "title",
                "El campo title no puede estar vacío ni contener solo espacios.",
            )
        if len(titulo) > MAX_TITULO:
            raise ValidationError(
                CREATE_TITULO_DEMASIADO_LARGO,
                "title",
                f"El campo title no puede superar {MAX_TITULO} caracteres.",
            )
        return titulo

    @staticmethod
    def _validar_creacion(instante: datetime) -> None:
        if not isinstance(instante, datetime) or (
            instante.tzinfo is not None and instante.tzinfo.utcoffset(instante) is not None
        ):
            raise ValidationError(
                CREATE_CREACION_INVALIDA,
                "created_at",
                "El instante de creación debe ser una fecha naive sin zona horaria.",
            )

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
