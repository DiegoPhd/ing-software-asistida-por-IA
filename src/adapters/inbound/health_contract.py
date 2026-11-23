"""Contrato de transporte compartido por HTTP y CLI para la salud (D1).

HTTP lo usa como `response_model` de `GET /health` y la CLI serializa el mismo
modelo con `model_dump(mode="json")`, de modo que ambos canales publican un
documento idéntico sin que la consola importe el adaptador HTTP. Ningún campo
expone motor, host, usuario, versión, latencia ni la causa del fallo.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Documento canónico de `contracts/health.schema.json`."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "error"]
    database: Literal["connected", "unavailable"]


def to_health_response(connected: bool) -> HealthResponse:
    """Fija la pareja válida: `True` → `ok`/`connected`, `False` → `error`/`unavailable`."""
    if connected:
        return HealthResponse(status="ok", database="connected")
    return HealthResponse(status="error", database="unavailable")
