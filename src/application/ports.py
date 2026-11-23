"""Puertos de salida de la capa de aplicación (Constitución §IV).

`IncidentRepositoryPort` es el único puerto vigente de H002: la política de SLA
es una constante del dominio y el instante de referencia es un argumento
explícito del caso de uso.
"""

from typing import Optional, Protocol, Sequence, runtime_checkable

from src.domain.models import Incident


@runtime_checkable
class IncidentRepositoryPort(Protocol):
    """Contrato persistido que debe cumplir todo adaptador de incidentes."""

    def save_incident(self, incident: Incident) -> None:
        """Registra o reemplaza un incidente validado."""
        ...

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Devuelve el incidente con ese identificador, o `None`."""
        ...

    def find_open_duplicates(self, incident: Incident) -> Sequence[Incident]:
        """Candidatos activos del mismo componente, sin similitud (H003)."""
        ...

    def list_active_incidents(
        self, component_filter: Optional[str]
    ) -> Sequence[Incident]:
        """Incidentes OPEN/IN_PROGRESS, opcionalmente de un componente."""
        ...

    def check_health(self) -> bool:
        """Señal de conectividad del almacenamiento."""
        ...
