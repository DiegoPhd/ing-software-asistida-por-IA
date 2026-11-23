"""Raíz de composición: selección del repositorio por `DATABASE_URL` (ADR-007).

Único punto que conoce clases concretas y el único que interpreta el DSN. El
inbound nunca instancia un repositorio ni lee la variable. La ausencia total de
la variable habilita la ruta local en memoria; un valor definido pero vacío es
un error de configuración y nunca cae a memoria en silencio (FR-006).
"""

import os
from typing import Optional

from src.adapters.outbound.postgres_repository import PostgresIncidentRepository
from src.adapters.outbound.sqlite_repository import SQLiteIncidentRepository
from src.adapters.outbound.system_clock import SystemClock
from src.application.ports import IncidentRepositoryPort
from src.application.services import IncidentService

ESQUEMA_POSTGRESQL = "postgresql"
ESQUEMA_SQLITE = "sqlite"
PREFIJO_SQLITE = "sqlite:///"
PREFIJO_SQLITE_GENERICO = "sqlite://"
PREFIJO_POSTGRESQL = "postgresql://"
MEMORIA = ":memory:"

OPCIONES_VALIDAS = (
    "Use 'sqlite:///ruta/incidentops.db', 'sqlite:///:memory:' o "
    "'postgresql://usuario:clave@host:5432/base'."
)
DETALLE_VACIO = "DATABASE_URL está definida pero vacía. " + OPCIONES_VALIDAS
DETALLE_SIN_RUTA = "DATABASE_URL no indica archivo ni memoria. " + OPCIONES_VALIDAS


class ConfigurationError(RuntimeError):
    """Configuración inválida de la fuente de datos."""


def _leer_database_url(database_url: Optional[str]) -> Optional[str]:
    """Lee el DSN explícito o, si se omite, el de `DATABASE_URL`."""
    return database_url if database_url is not None else os.getenv("DATABASE_URL")


def _esquema(url: str) -> str:
    """Devuelve solo el esquema del DSN para mensajes sin credenciales."""
    return url.split("://", 1)[0] if "://" in url else url


def _error_de_esquema(url: str) -> ConfigurationError:
    """Error que cita como máximo el esquema, nunca el DSN ni credenciales."""
    return ConfigurationError(
        f"Esquema de DATABASE_URL no soportado: '{_esquema(url)}'. " + OPCIONES_VALIDAS
    )


def resolve_database_path(database_url: Optional[str] = None) -> str:
    """Traduce `DATABASE_URL` a la ruta que espera `sqlite3`.

    Ausente → memoria; `sqlite:///:memory:` → memoria; `sqlite:///ruta` →
    archivo; cualquier otro esquema o valor vacío → error de configuración sin
    intentar abrir nada.
    """
    url = _leer_database_url(database_url)
    if url is None:
        return MEMORIA
    limpia = url.strip()
    if not limpia:
        raise ConfigurationError(DETALLE_VACIO)
    if limpia == PREFIJO_SQLITE_GENERICO:
        raise ConfigurationError(DETALLE_SIN_RUTA)
    if not limpia.startswith(PREFIJO_SQLITE):
        raise _error_de_esquema(limpia)
    ruta = limpia[len(PREFIJO_SQLITE):]
    if not ruta.strip():
        raise ConfigurationError(DETALLE_SIN_RUTA)
    return ruta


def create_repository(database_url: Optional[str] = None) -> IncidentRepositoryPort:
    """Construye el repositorio concreto a partir del DSN."""
    url = _leer_database_url(database_url)
    if url is None:
        return SQLiteIncidentRepository(MEMORIA)

    limpia = url.strip()
    if not limpia:
        raise ConfigurationError(DETALLE_VACIO)
    if limpia.startswith(PREFIJO_POSTGRESQL):
        if not limpia[len(PREFIJO_POSTGRESQL):]:
            raise ConfigurationError(
                "DATABASE_URL no incluye usuario, host ni base. " + OPCIONES_VALIDAS
            )
        return PostgresIncidentRepository(limpia)
    if limpia.startswith(PREFIJO_SQLITE_GENERICO):
        return SQLiteIncidentRepository(resolve_database_path(limpia))
    raise _error_de_esquema(limpia)


def build_incident_service(database_url: Optional[str] = None) -> IncidentService:
    """Ensambla el caso de uso con su persistencia y el reloj del sistema."""
    return IncidentService(create_repository(database_url), clock=SystemClock())
