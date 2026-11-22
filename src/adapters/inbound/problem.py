"""Construcción compartida del documento de error RFC 9457 (problem+json).

REST y CLI presentan el mismo código estable; solo cambia el canal de salida.
"""

from typing import Any, Dict

BASE_URL = "https://incidentops.local/errores/"

_TITULOS: Dict[str, str] = {
    "TRIAGE_ID_VACIO": "Identificador de incidente vacío",
    "TRIAGE_TEXTO_VACIO": "Texto de reporte vacío",
    "TRIAGE_ID_DEMASIADO_LARGO": "Identificador de incidente demasiado largo",
    "TRIAGE_TEXTO_DEMASIADO_LARGO": "Texto de reporte demasiado largo",
    "TRIAGE_SOLICITUD_INVALIDA": "Solicitud inválida",
    "TRIAGE_FUENTE_TEXTO_INVALIDA": "Fuente de texto inválida",
    "TRIAGE_ARCHIVO_INVALIDO": "Archivo de reporte inválido",
    "TRIAGE_ID_CONFLICTO": "Identificador de incidente en conflicto",
}


def titulo_para(code: str) -> str:
    """Título legible para un código de error del triaje."""
    return _TITULOS.get(code, "Error de triaje")


def build_problem(
    code: str, field: str, detail: str, status: int = 422
) -> Dict[str, Any]:
    """Devuelve el documento problem+json con el código estable del adaptador."""
    return {
        "type": f"{BASE_URL}{code.lower().replace('_', '-')}",
        "title": titulo_para(code),
        "status": status,
        "detail": detail,
        "code": code,
        "errors": [{"field": field, "code": code}],
    }
