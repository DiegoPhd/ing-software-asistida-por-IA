"""Raíz de composición: selección del repositorio por `DATABASE_URL` (D5).

Único punto que conoce clases concretas. El inbound nunca instancia un
repositorio ni interpreta el DSN.
"""

import os
from typing import Optional

from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.adapters.outbound.system_clock import SystemClock
from src.application.ports import IncidentRepositoryPort
from src.application.services import IncidentService

PREFIJO_SQLITE = "sqlite:///"
MEMORIA = ":memory:"


class ConfigurationError(RuntimeError):
    """Configuración inválida de la fuente de datos."""


def resolve_database_path(database_url: Optional[str] = None) -> str:
    """Traduce `DATABASE_URL` a la ruta que espera `sqlite3`.

    Ausente o `sqlite:///:memory:` → memoria; `sqlite:///ruta` → archivo; otro
    esquema → error de configuración sin intentar abrir nada.
    """
    url = database_url if database_url is not None else os.getenv("DATABASE_URL")
    if not url:
        return MEMORIA
    if not url.startswith(PREFIJO_SQLITE):
        esquema = url.split("://", 1)[0] if "://" in url else url
        raise ConfigurationError(
            f"Esquema de DATABASE_URL no soportado: '{esquema}'. "
            "Use 'sqlite:///ruta/incidentops.db' o 'sqlite:///:memory:'."
        )
    ruta = url[len(PREFIJO_SQLITE):]
    if not ruta:
        raise ConfigurationError(
            "DATABASE_URL no indica archivo ni memoria: "
            "use 'sqlite:///ruta/incidentops.db' o 'sqlite:///:memory:'."
        )
    return ruta


def create_repository(database_url: Optional[str] = None) -> IncidentRepositoryPort:
    """Construye el repositorio concreto a partir del DSN."""
    return SQLiteIncidentRepository(resolve_database_path(database_url))


def build_incident_service(database_url: Optional[str] = None) -> IncidentService:
    """Ensambla el caso de uso con su persistencia y el reloj del sistema."""
    return IncidentService(create_repository(database_url), clock=SystemClock())
