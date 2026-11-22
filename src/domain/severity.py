"""Catálogo cerrado de severidades, componentes y equipos (Constitución §1.2 y §1.5)."""

from typing import Dict, Literal

SeverityLevel = Literal["P0", "P1", "P2", "P3"]

Team = Literal["Backend-Core", "Security-IAM", "Data-DBA", "Platform-SRE", "otros"]

COMPONENT_TEAM: Dict[str, Team] = {
    "payments-gateway": "Backend-Core",
    "auth-identity": "Security-IAM",
    "database-cluster": "Data-DBA",
    "infra-certificates": "Platform-SRE",
    "security-audit": "Security-IAM",
    "reporting-api": "otros",
}

DEFAULT_COMPONENT = "reporting-api"


def team_for_component(component: str) -> Team:
    """Devuelve el equipo responsable de un componente del catálogo cerrado."""
    try:
        return COMPONENT_TEAM[component]
    except KeyError as exc:
        raise ValueError(f"Componente fuera del catálogo de dominio: {component}") from exc
