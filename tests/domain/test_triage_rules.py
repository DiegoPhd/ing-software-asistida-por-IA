"""Pruebas table-driven de las reglas puras de triaje."""

import pytest

from src.domain.triage_rules import classify_impact
from tests.conftest import cargar_reportes_de_muestra

ESPERADOS = {
    "INC-1001": ("P0", "payments-gateway", "Backend-Core"),
    "INC-1002": ("P2", "auth-identity", "Security-IAM"),
    "INC-1003": ("P2", "reporting-api", "otros"),
    "INC-1004": ("P3", "reporting-api", "otros"),
    "INC-1005": ("P1", "database-cluster", "Data-DBA"),
    "INC-1006": ("P0", "payments-gateway", "Backend-Core"),
    "INC-1007": ("P0", "security-audit", "Security-IAM"),
    "INC-1008": ("P2", "reporting-api", "otros"),
    "INC-1009": ("P2", "reporting-api", "otros"),
    "INC-1010": ("P3", "infra-certificates", "Platform-SRE"),
}

CASOS = [
    (reporte["id"], reporte["raw_text"], *ESPERADOS[reporte["id"]])
    for reporte in cargar_reportes_de_muestra()
]


@pytest.mark.parametrize("incident_id, texto, severidad, componente, equipo", CASOS)
def test_clasificacion_de_los_reportes_de_muestra(
    incident_id: str,
    texto: str,
    severidad: str,
    componente: str,
    equipo: str,
) -> None:
    resultado = classify_impact(incident_id, texto)

    assert resultado.incident_id == incident_id
    assert resultado.severity == severidad
    assert resultado.component == componente
    assert resultado.recommended_team == equipo
    assert resultado.duplicate_group_key is None
    assert resultado.rationale


def test_palabras_emocionales_no_escalan_a_p0() -> None:
    resultado = classify_impact(
        "INC-2001",
        "URGENTE, es para hoy: mi cuenta aparece bloqueada y necesito acceder.",
    )

    assert resultado.severity == "P2"
    assert resultado.recommended_team == "Security-IAM"


def test_reporte_sin_palabras_clave_usa_el_valor_por_defecto() -> None:
    resultado = classify_impact("INC-2002", "El sistema reporta un comportamiento raro.")

    assert resultado.severity == "P2"
    assert resultado.component == "reporting-api"
    assert resultado.recommended_team == "otros"


def test_pagos_gana_sobre_gateway_en_el_enrutamiento() -> None:
    resultado = classify_impact(
        "INC-2003",
        "El gateway de pagos devuelve HTTP 502 en las transacciones con tarjeta.",
    )

    assert resultado.component == "payments-gateway"
    assert resultado.recommended_team == "Backend-Core"


def test_la_clasificacion_es_determinista() -> None:
    texto = "El pool de conexiones de PostgreSQL está saturado con timeouts."

    primera = classify_impact("INC-2004", texto)
    segunda = classify_impact("INC-2004", texto)

    assert primera == segunda


def test_el_resultado_no_es_mutable() -> None:
    resultado = classify_impact("INC-2005", "El botón de exportar cambió de color.")

    with pytest.raises(Exception):
        resultado.severity = "P0"  # type: ignore[misc]
