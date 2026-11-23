"""Traducción de errores de aplicación y de validación al formato problem+json.

El prefijo del código estable se elige por ruta: `SUMMARY_*` para el resumen y
`TRIAGE_*` para el triaje, sin duplicar manejadores.
"""

from typing import Any, Dict, List

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.adapters.inbound.problem import build_problem
from src.application.services import DataInconsistencyError, ValidationError

PROBLEM_JSON = "application/problem+json"


def _es_resumen(request: Request) -> bool:
    return request.url.path.rstrip("/").endswith("/incidents/summary")


def _prefijo(request: Request) -> str:
    return "SUMMARY" if _es_resumen(request) else "TRIAGE"


def _codigo_solicitud(request: Request) -> str:
    return f"{_prefijo(request)}_SOLICITUD_INVALIDA"


def _codigo_interno(request: Request) -> str:
    return f"{_prefijo(request)}_ERROR_INTERNO"


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


async def manejar_inconsistencia_de_datos(
    _request: Request, exc: DataInconsistencyError
) -> JSONResponse:
    """Traduce un dato almacenado incoherente a 409 sin totales parciales."""
    return _respuesta(build_problem(exc.code, exc.field, exc.detail, status=409))


async def manejar_validacion_de_esquema(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Sustituye el 422 por defecto de FastAPI por el contrato problem+json."""
    code = _codigo_solicitud(request)
    campos: List[Dict[str, str]] = []
    for error in exc.errors():
        ubicacion = [
            str(parte)
            for parte in error.get("loc", ())
            if parte not in ("body", "query")
        ]
        campos.append(
            {
                "field": ".".join(ubicacion) or "request",
                "code": code,
            }
        )

    detalle = (
        "La solicitud del resumen no cumple el esquema esperado."
        if _es_resumen(request)
        else "La solicitud no cumple el esquema esperado: se requieren incident_id y raw_text como texto."
    )
    documento = build_problem(
        code,
        campos[0]["field"] if campos else "request",
        detalle,
        status=422,
    )
    documento["errors"] = campos
    return _respuesta(documento)


async def manejar_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Mantiene el formato problem+json también en los errores HTTP del framework."""
    code = _codigo_solicitud(request) if exc.status_code < 500 else _codigo_interno(request)
    documento = build_problem(
        code,
        "request",
        str(exc.detail),
        status=exc.status_code,
    )
    return _respuesta(documento)


async def manejar_error_inesperado(request: Request, _exc: Exception) -> JSONResponse:
    """Traduce cualquier fallo no previsto a 500 sin exponer detalles internos."""
    documento = build_problem(
        _codigo_interno(request),
        "request",
        "El servidor no pudo completar la solicitud.",
        status=500,
    )
    return _respuesta(documento)
