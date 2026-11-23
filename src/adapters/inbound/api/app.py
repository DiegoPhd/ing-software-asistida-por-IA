"""Aplicación FastAPI de los adaptadores REST de triaje, resumen y ciclo de vida."""

import os
from dataclasses import asdict
from typing import List, Optional, Set

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.adapters.inbound.api.errors import (
    manejar_error_inesperado,
    manejar_http_exception,
    manejar_inconsistencia_de_datos,
    manejar_incidente_no_encontrado,
    manejar_incidente_ya_existe,
    manejar_validacion_de_aplicacion,
    manejar_validacion_de_esquema,
)
from src.adapters.inbound.api.schemas import TriageRequest, TriageResponse
from src.adapters.inbound.lifecycle_contract import (
    CreateIncidentRequest,
    IncidentCreatedResponse,
    SLAEvaluationResponse,
    to_incident_created_response,
    to_sla_evaluation_response,
)
from src.adapters.inbound.summary_contract import (
    ActiveIncidentsSummaryResponse,
    parse_reference_time,
    to_summary_response,
)
from src.adapters.inbound.temporal_contract import parse_instante_naive
from src.adapters.outbound.factory import build_incident_service
from src.application.services import (
    CREATE_CREACION_INVALIDA,
    CREATE_SOLICITUD_INVALIDA,
    SLA_REFERENCIA_INVALIDA,
    SLA_SOLICITUD_INVALIDA,
    SUMMARY_SOLICITUD_INVALIDA,
    DataInconsistencyError,
    IncidentAlreadyExistsError,
    IncidentNotFoundError,
    IncidentService,
    ValidationError,
)

TITULO = "IncidentOps · Operación"
RUTA_INCIDENTES = "/api/v1/incidents"
RUTA_RESUMEN = "/api/v1/incidents/summary"
RUTA_SLA = "/api/v1/incidents/{incident_id}/sla"
PARAMETROS_RESUMEN: Set[str] = {"component", "reference_time"}
PARAMETROS_ALTA: Set[str] = set()
PARAMETROS_SLA: Set[str] = {"reference_time"}


def _origenes_cors() -> List[str]:
    """Lee los orígenes permitidos de `INCIDENTOPS_CORS_ORIGINS`."""
    crudo = os.getenv("INCIDENTOPS_CORS_ORIGINS", "")
    return [origen.strip() for origen in crudo.split(",") if origen.strip()]


def _rechazar_parametros(
    request: Request, permitidos: Set[str], codigo: str, recurso: str
) -> None:
    """Rechaza parámetros desconocidos o repetidos fuera del contrato."""
    for nombre in request.query_params.keys():
        if nombre not in permitidos:
            raise ValidationError(
                codigo,
                nombre,
                f"El parámetro '{nombre}' no forma parte del contrato del {recurso}.",
            )
    for nombre in permitidos:
        if len(request.query_params.getlist(nombre)) > 1:
            raise ValidationError(
                codigo,
                nombre,
                f"El parámetro '{nombre}' no puede repetirse.",
            )


def create_app(service: Optional[IncidentService] = None) -> FastAPI:
    """Construye la aplicación inyectando el caso de uso compartido."""
    aplicacion = FastAPI(title=TITULO, version="0.3.0")
    caso_de_uso = service or build_incident_service()

    origenes = _origenes_cors()
    if origenes:
        aplicacion.add_middleware(
            CORSMiddleware,
            allow_origins=origenes,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    aplicacion.add_exception_handler(
        ValidationError, manejar_validacion_de_aplicacion
    )
    aplicacion.add_exception_handler(
        DataInconsistencyError, manejar_inconsistencia_de_datos
    )
    aplicacion.add_exception_handler(
        IncidentAlreadyExistsError, manejar_incidente_ya_existe
    )
    aplicacion.add_exception_handler(
        IncidentNotFoundError, manejar_incidente_no_encontrado
    )
    aplicacion.add_exception_handler(
        RequestValidationError, manejar_validacion_de_esquema
    )
    aplicacion.add_exception_handler(StarletteHTTPException, manejar_http_exception)
    aplicacion.add_exception_handler(Exception, manejar_error_inesperado)

    @aplicacion.get("/health")
    def health() -> dict:
        """Señal de vida del servicio."""
        return {"status": "ok"}

    @aplicacion.post(
        "/api/v1/incidents/triage",
        response_model=TriageResponse,
    )
    def triage(payload: TriageRequest) -> TriageResponse:
        """Clasifica un reporte y devuelve severidad, componente y equipo."""
        resultado = caso_de_uso.triage_incident(payload.incident_id, payload.raw_text)
        return TriageResponse(**asdict(resultado))

    @aplicacion.get(
        RUTA_RESUMEN,
        response_model=ActiveIncidentsSummaryResponse,
    )
    def summary(
        request: Request,
        component: Optional[str] = None,
        reference_time: Optional[str] = None,
    ) -> ActiveIncidentsSummaryResponse:
        """Devuelve totales y detalle de los incidentes activos."""
        _rechazar_parametros(
            request, PARAMETROS_RESUMEN, SUMMARY_SOLICITUD_INVALIDA, "resumen"
        )
        instante = parse_reference_time(reference_time)
        resumen = caso_de_uso.get_active_incidents_summary(
            reference_time=instante,
            component_filter=component,
        )
        return to_summary_response(resumen)

    @aplicacion.post(
        RUTA_INCIDENTES,
        response_model=IncidentCreatedResponse,
        status_code=201,
    )
    def create_incident(
        request: Request, payload: CreateIncidentRequest
    ) -> IncidentCreatedResponse:
        """Registra un incidente y devuelve su clasificación y aviso de duplicados."""
        _rechazar_parametros(request, PARAMETROS_ALTA, CREATE_SOLICITUD_INVALIDA, "alta")
        instante = parse_instante_naive(
            payload.created_at, "created_at", CREATE_CREACION_INVALIDA
        )
        resultado = caso_de_uso.create_incident(
            payload.incident_id,
            payload.raw_text,
            title=payload.title,
            created_at=instante,
        )
        return to_incident_created_response(resultado)

    @aplicacion.get(
        RUTA_SLA,
        response_model=SLAEvaluationResponse,
    )
    def evaluate_sla(
        request: Request,
        incident_id: str,
        reference_time: Optional[str] = None,
    ) -> SLAEvaluationResponse:
        """Audita el SLA de un incidente en un instante de referencia único."""
        _rechazar_parametros(request, PARAMETROS_SLA, SLA_SOLICITUD_INVALIDA, "SLA")
        if not incident_id.strip():
            raise ValidationError(
                SLA_SOLICITUD_INVALIDA,
                "incident_id",
                "El identificador del incidente no puede estar compuesto solo por espacios.",
            )
        instante = parse_instante_naive(
            reference_time, "reference_time", SLA_REFERENCIA_INVALIDA
        )
        detalle = caso_de_uso.evaluate_incident_sla(incident_id, instante)
        return to_sla_evaluation_response(detalle)

    return aplicacion


app = create_app()
