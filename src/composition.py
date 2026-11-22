"""Raíz de composición: único punto que conoce las clases concretas."""

from src.application.services import IncidentService


def build_incident_service() -> IncidentService:
    """Ensambla el caso de uso de triaje para los adaptadores de entrada."""
    return IncidentService()
