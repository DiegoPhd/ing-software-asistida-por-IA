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
    "TRIAGE_ERROR_INTERNO": "Error interno al clasificar el reporte",
    "SUMMARY_COMPONENTE_DEMASIADO_LARGO": "Componente del filtro demasiado largo",
    "SUMMARY_REFERENCIA_INVALIDA": "Instante de referencia inválido",
    "SUMMARY_SOLICITUD_INVALIDA": "Solicitud de resumen inválida",
    "SUMMARY_REFERENCIA_INCONSISTENTE": "Instante de referencia incoherente con los datos",
    "SUMMARY_ERROR_INTERNO": "Error interno al construir el resumen",
    "CREATE_ID_VACIO": "Identificador de incidente vacío",
    "CREATE_ID_DEMASIADO_LARGO": "Identificador de incidente demasiado largo",
    "CREATE_TEXTO_VACIO": "Texto de reporte vacío",
    "CREATE_TEXTO_DEMASIADO_LARGO": "Texto de reporte demasiado largo",
    "CREATE_TITULO_VACIO": "Título de incidente vacío",
    "CREATE_TITULO_DEMASIADO_LARGO": "Título de incidente demasiado largo",
    "CREATE_CREACION_INVALIDA": "Instante de creación inválido",
    "CREATE_SOLICITUD_INVALIDA": "Solicitud de alta inválida",
    "CREATE_ID_CONFLICTO": "Identificador de incidente ya registrado",
    "CREATE_ERROR_INTERNO": "Error interno al registrar el incidente",
    "SLA_ID_VACIO": "Identificador de incidente vacío",
    "SLA_REFERENCIA_INVALIDA": "Instante de referencia inválido",
    "SLA_SOLICITUD_INVALIDA": "Solicitud de SLA inválida",
    "SLA_REFERENCIA_INCONSISTENTE": "Instante de referencia anterior a la creación",
    "SLA_DATOS_INCONSISTENTES": "Datos del incidente incoherentes",
    "SLA_INCIDENTE_NO_ENCONTRADO": "Incidente no encontrado",
    "SLA_ERROR_INTERNO": "Error interno al auditar el SLA",
    "CONFIG_DATABASE_URL_INVALIDA": "Configuración de base de datos inválida",
    "HEALTH_ERROR_INTERNO": "Error interno al comprobar la salud",
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
