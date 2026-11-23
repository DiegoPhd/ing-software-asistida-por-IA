"""Reglas puras de triaje por impacto real y enrutamiento por componente.

Sin reloj, sin persistencia, sin `print` y sin dependencias de transporte:
la misma entrada produce siempre la misma salida.
"""

from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher
from types import MappingProxyType
from typing import Mapping, Optional, Sequence, Tuple

from src.domain.models import ACTIVE_STATUSES, Incident
from src.domain.severity import SeverityLevel, Team, team_for_component

__all__ = [
    "DUPLICATE_SIMILARITY_THRESHOLD",
    "DUPLICATE_WINDOW_DAYS",
    "DuplicateAssessment",
    "TriageResult",
    "assess_duplicates",
    "classify_impact",
    "is_equivalent",
]

DUPLICATE_SIMILARITY_THRESHOLD = 0.75

# Ventana de la severidad del incidente más antiguo del par (Constitución §1.4).
DUPLICATE_WINDOW_DAYS: Mapping[SeverityLevel, int] = MappingProxyType(
    {"P0": 1, "P1": 2, "P2": 3, "P3": 4}
)


@dataclass(frozen=True)
class TriageResult:
    """Resultado determinista del triaje de un reporte de incidente."""

    incident_id: str
    severity: SeverityLevel
    component: str
    recommended_team: Team
    rationale: str
    duplicate_group_key: Optional[str] = None


@dataclass(frozen=True)
class DuplicateAssessment:
    """Veredicto informativo de equivalencia con incidentes previos."""

    duplicate_group_key: Optional[str]
    duplicate_of: Tuple[str, ...]

    @property
    def is_duplicate(self) -> bool:
        """Verdadera si y sólo si hay equivalentes previos."""
        return bool(self.duplicate_of)


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


def _clave_canonica(incident: Incident) -> Tuple[object, str]:
    """Orden canónico del lote: instante de creación y, en empate, identificador."""
    return (incident.created_at, incident.incident_id)


def _similitud(primero: str, segundo: str) -> float:
    """Similitud de `SequenceMatcher` sobre el texto en minúsculas."""
    return SequenceMatcher(None, primero.lower(), segundo.lower()).ratio()


def is_equivalent(older: Incident, newer: Incident) -> bool:
    """Decide si dos incidentes son equivalentes según la regla vigente.

    Sólo cuentan candidatos activos, del mismo componente, con identificador
    distinto y texto original no vacío. La ventana aplicable es la de la
    severidad del más antiguo del par y el límite exacto es equivalente.
    """
    primero, segundo = sorted((older, newer), key=_clave_canonica)
    if primero.status not in ACTIVE_STATUSES:
        return False
    if primero.component != segundo.component:
        return False
    if primero.incident_id == segundo.incident_id:
        return False

    texto_primero = (primero.raw_text or "").strip()
    texto_segundo = (segundo.raw_text or "").strip()
    if not texto_primero or not texto_segundo:
        return False

    ventana_dias = DUPLICATE_WINDOW_DAYS.get(primero.severity)
    if ventana_dias is None:
        return False
    diferencia = segundo.created_at - primero.created_at
    if not (timedelta(0) <= diferencia <= timedelta(days=ventana_dias)):
        return False

    return _similitud(texto_primero, texto_segundo) >= DUPLICATE_SIMILARITY_THRESHOLD


def assess_duplicates(
    new_incident: Incident, candidates: Sequence[Incident]
) -> DuplicateAssessment:
    """Evalúa los candidatos estructurales y devuelve el aviso de duplicados.

    Sólo los equivalentes que preceden al nuevo en el orden canónico entran en
    `duplicate_of`, de más antiguo a más reciente. La clave del grupo es la del
    original más antiguo o la que ese original ya hubiera heredado.
    """
    nuevo = _clave_canonica(new_incident)
    previos = [
        candidato
        for candidato in candidates
        if _clave_canonica(candidato) < nuevo
        and is_equivalent(candidato, new_incident)
    ]
    if not previos:
        return DuplicateAssessment(None, ())

    previos.sort(key=_clave_canonica)
    original = previos[0]
    return DuplicateAssessment(
        duplicate_group_key=original.duplicate_group_key or original.incident_id,
        duplicate_of=tuple(candidato.incident_id for candidato in previos),
    )
