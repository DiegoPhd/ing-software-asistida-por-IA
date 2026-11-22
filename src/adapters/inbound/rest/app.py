"""Aplicación FastAPI del adaptador REST de triaje."""

import os
from dataclasses import asdict
from typing import List, Optional

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.adapters.inbound.rest.errors import (
    manejar_http_exception,
    manejar_validacion_de_aplicacion,
    manejar_validacion_de_esquema,
)
from src.adapters.inbound.rest.schemas import TriageRequest, TriageResponse
from src.application.errors import TriageValidationError
from src.application.incident_service import IncidentService
from src.composition import build_incident_service

TITULO = "IncidentOps · Triaje"


def _origenes_cors() -> List[str]:
    """Lee los orígenes permitidos de `INCIDENTOPS_CORS_ORIGINS`."""
    crudo = os.getenv("INCIDENTOPS_CORS_ORIGINS", "")
    return [origen.strip() for origen in crudo.split(",") if origen.strip()]


def create_app(service: Optional[IncidentService] = None) -> FastAPI:
    """Construye la aplicación inyectando el caso de uso compartido."""
    aplicacion = FastAPI(title=TITULO, version="0.1.0")
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
        TriageValidationError, manejar_validacion_de_aplicacion
    )
    aplicacion.add_exception_handler(
        RequestValidationError, manejar_validacion_de_esquema
    )
    aplicacion.add_exception_handler(StarletteHTTPException, manejar_http_exception)

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

    return aplicacion


app = create_app()
