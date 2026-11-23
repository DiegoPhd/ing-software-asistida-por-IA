"""Puertos de salida de la capa de aplicación (Constitución §IV).

`IncidentRepositoryPort` conserva la firma de H002 y precisa la semántica de
escritura; `ClockPort` incorpora el reloj como puerto secundario cuando el caso
de uso debe resolver el instante actual (H003).
"""

from datetime import datetime
from typing import Optional, Protocol, Sequence, runtime_checkable

from src.domain.models import Incident


@runtime_checkable
class IncidentRepositoryPort(Protocol):
    """Contrato persistido que debe cumplir todo adaptador de incidentes."""

    def save_incident(self, incident: Incident) -> None:
        """Inserta un incidente validado y rechaza el conflicto de identificador.

        Nunca reemplaza ni fusiona: un identificador ya almacenado se informa
        como conflicto para que el alta no sobrescriba el incidente previo
        (FR-008/FR-016).
        """
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


@runtime_checkable
class ClockPort(Protocol):
    """Reloj inyectable para resolver el instante de la solicitud una sola vez."""

    def now(self) -> datetime:
        """Devuelve el instante actual como fecha naive local."""
        ...
