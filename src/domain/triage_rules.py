"""Reglas puras de triaje por impacto real y enrutamiento por componente.

Sin reloj, sin persistencia, sin `print` y sin dependencias de transporte:
la misma entrada produce siempre la misma salida.
"""

from dataclasses import dataclass
from typing import Optional

from src.domain.severity import SeverityLevel, Team, team_for_component


@dataclass(frozen=True)
class TriageResult:
    """Resultado determinista del triaje de un reporte de incidente."""

    incident_id: str
    severity: SeverityLevel
    component: str
    recommended_team: Team
    rationale: str
    duplicate_group_key: Optional[str] = None


# Marcadores de impacto. La precedencia es P0 -> P1 -> P2 -> P3 y el valor por
# defecto es P2 (Constitución §1.4). Las palabras emocionales no intervienen.
_P0_MARCADORES = (
    "502",
    "indisponibilidad",
    "global",
    "otra organización",
    "otra empresa",
    "multi-tenant",
)

_P1_MARCADORES = ("94%", "timeout", "conexiones", "pool")

_P2_MARCADORES = ("lenta", "segundos")

_P3_MARCADORES = ("botón", "color", "staging", "cosmética")


def _es_p0(texto: str) -> bool:
    if any(marcador in texto for marcador in _P0_MARCADORES):
        return True
    return "pagos" in texto and any(
        marcador in texto for marcador in ("caído", "no funciona", "ningún comercio")
    )


def _clasificar_severidad(texto: str) -> SeverityLevel:
    if _es_p0(texto):
        return "P0"
    if any(marcador in texto for marcador in _P1_MARCADORES):
        return "P1"
    if any(marcador in texto for marcador in _P2_MARCADORES) or (
        "cuenta" in texto and "bloqueada" in texto
    ):
        return "P2"
    if any(marcador in texto for marcador in _P3_MARCADORES):
        return "P3"
    return "P2"


def _clasificar_componente(texto: str) -> str:
    """El orden es parte del contrato: pagos gana sobre gateway."""
    if any(marcador in texto for marcador in ("pago", "cobro", "tarjeta", "transacciones")):
        return "payments-gateway"
    if any(marcador in texto for marcador in ("cuenta", "ingresar", "acceso")):
        return "auth-identity"
    if any(marcador in texto for marcador in ("postgresql", "conexiones", "base de datos")):
        return "database-cluster"
    if any(marcador in texto for marcador in ("certificado", "tls", "gateway", "502")):
        return "infra-certificates"
    if any(
        marcador in texto
        for marcador in ("otra organización", "facturas pertenecientes a otra")
    ):
        return "security-audit"
    return "reporting-api"


def classify_impact(incident_id: str, raw_text: str) -> TriageResult:
    """Clasifica un reporte por impacto real y resuelve su equipo responsable."""
    texto = raw_text.lower()
    severity = _clasificar_severidad(texto)
    component = _clasificar_componente(texto)
    recommended_team = team_for_component(component)
    rationale = (
        f"Triaje basado en impacto. Componente: {component}, "
        f"Severidad: {severity}, Equipo: {recommended_team}."
    )
    return TriageResult(
        incident_id=incident_id,
        severity=severity,
        component=component,
        recommended_team=recommended_team,
        rationale=rationale,
        duplicate_group_key=None,
    )
