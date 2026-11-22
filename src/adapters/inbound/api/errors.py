"""Traducción de errores de aplicación y de validación al formato problem+json."""

from typing import Any, Dict, List

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.adapters.inbound.problem import build_problem
from src.application.services import ValidationError

PROBLEM_JSON = "application/problem+json"
TRIAGE_SOLICITUD_INVALIDA = "TRIAGE_SOLICITUD_INVALIDA"


def _respuesta(documento: Dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        status_code=documento["status"],
        content=documento,
        media_type=PROBLEM_JSON,
    )


async def manejar_validacion_de_aplicacion(
    _request: Request, exc: ValidationError
) -> JSONResponse:
    """Traduce una regla de entrada del caso de uso a 422 problem+json."""
    return _respuesta(build_problem(exc.code, exc.field, exc.detail, status=422))


async def manejar_validacion_de_esquema(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Sustituye el 422 por defecto de FastAPI por el contrato problem+json."""
    campos: List[Dict[str, str]] = []
    for error in exc.errors():
        ubicacion = [str(parte) for parte in error.get("loc", ()) if parte != "body"]
        campos.append(
            {
                "field": ".".join(ubicacion) or "body",
                "code": TRIAGE_SOLICITUD_INVALIDA,
            }
        )
    documento = build_problem(
        TRIAGE_SOLICITUD_INVALIDA,
        campos[0]["field"] if campos else "body",
        "La solicitud no cumple el esquema esperado: se requieren incident_id y raw_text como texto.",
        status=422,
    )
    documento["errors"] = campos
    return _respuesta(documento)


async def manejar_http_exception(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Mantiene el formato problem+json también en los errores HTTP del framework."""
    code = "TRIAGE_SOLICITUD_INVALIDA" if exc.status_code < 500 else "TRIAGE_ERROR_INTERNO"
    documento = build_problem(
        code,
        "request",
        str(exc.detail),
        status=exc.status_code,
    )
    return _respuesta(documento)
