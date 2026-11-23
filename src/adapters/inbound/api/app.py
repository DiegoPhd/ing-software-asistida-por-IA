"""Aplicación FastAPI de los adaptadores REST de triaje y resumen."""

import os
from dataclasses import asdict
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.adapters.inbound.api.errors import (
    manejar_error_inesperado,
    manejar_http_exception,
    manejar_inconsistencia_de_datos,
    manejar_validacion_de_aplicacion,
    manejar_validacion_de_esquema,
)
from src.adapters.inbound.api.schemas import TriageRequest, TriageResponse
from src.adapters.inbound.summary_contract import (
    ActiveIncidentsSummaryResponse,
    parse_reference_time,
    to_summary_response,
)
from src.adapters.outbound.factory import build_incident_service
from src.application.services import (
    SUMMARY_SOLICITUD_INVALIDA,
    DataInconsistencyError,
    IncidentService,
    ValidationError,
)

TITULO = "IncidentOps · Operación"
RUTA_RESUMEN = "/api/v1/incidents/summary"
PARAMETROS_RESUMEN = {"component", "reference_time"}


def _origenes_cors() -> List[str]:
    """Lee los orígenes permitidos de `INCIDENTOPS_CORS_ORIGINS`."""
    crudo = os.getenv("INCIDENTOPS_CORS_ORIGINS", "")
    return [origen.strip() for origen in crudo.split(",") if origen.strip()]


def _rechazar_parametros_desconocidos(request: Request) -> None:
    """Rechaza con 422 cualquier parámetro fuera del contrato del resumen."""
    for nombre in request.query_params.keys():
        if nombre not in PARAMETROS_RESUMEN:
            raise ValidationError(
                SUMMARY_SOLICITUD_INVALIDA,
                nombre,
                f"El parámetro '{nombre}' no forma parte del contrato del resumen.",
            )
    for nombre in PARAMETROS_RESUMEN:
        if len(request.query_params.getlist(nombre)) > 1:
            raise ValidationError(
                SUMMARY_SOLICITUD_INVALIDA,
                nombre,
                f"El parámetro '{nombre}' no puede repetirse.",
            )


def create_app(service: Optional[IncidentService] = None) -> FastAPI:
    """Construye la aplicación inyectando el caso de uso compartido."""
    aplicacion = FastAPI(title=TITULO, version="0.2.0")
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
        _rechazar_parametros_desconocidos(request)
        instante = parse_reference_time(reference_time)
        resumen = caso_de_uso.get_active_incidents_summary(
            reference_time=instante,
            component_filter=component,
        )
        return to_summary_response(resumen)

    return aplicacion


app = create_app()
