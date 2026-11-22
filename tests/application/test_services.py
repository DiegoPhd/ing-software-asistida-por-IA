"""Pruebas del caso de uso de triaje."""

import pytest

from src.application.services import (
    TRIAGE_ID_DEMASIADO_LARGO,
    TRIAGE_ID_VACIO,
    TRIAGE_TEXTO_DEMASIADO_LARGO,
    TRIAGE_TEXTO_VACIO,
    IncidentService,
    ValidationError,
)


@pytest.fixture()
def servicio() -> IncidentService:
    return IncidentService()


def test_triaje_valido_delega_en_el_dominio(servicio: IncidentService) -> None:
    resultado = servicio.triage_incident(
        "INC-1001", "HTTP 502 en el gateway de pagos con transacciones con tarjeta."
    )

    assert resultado.severity == "P0"
    assert resultado.component == "payments-gateway"
    assert resultado.recommended_team == "Backend-Core"
    assert resultado.duplicate_group_key is None


def test_texto_vacio_es_rechazado(servicio: IncidentService) -> None:
    with pytest.raises(ValidationError) as excinfo:
        servicio.triage_incident("INC-1001", "   ")

    assert excinfo.value.code == TRIAGE_TEXTO_VACIO
    assert excinfo.value.field == "raw_text"


def test_identificador_vacio_es_rechazado(servicio: IncidentService) -> None:
    with pytest.raises(ValidationError) as excinfo:
        servicio.triage_incident("  ", "Texto con impacto real.")

    assert excinfo.value.code == TRIAGE_ID_VACIO
    assert excinfo.value.field == "incident_id"


def test_identificador_demasiado_largo_es_rechazado(servicio: IncidentService) -> None:
    with pytest.raises(ValidationError) as excinfo:
        servicio.triage_incident("I" * 65, "Texto con impacto real.")

    assert excinfo.value.code == TRIAGE_ID_DEMASIADO_LARGO


def test_texto_demasiado_largo_es_rechazado(servicio: IncidentService) -> None:
    with pytest.raises(ValidationError) as excinfo:
        servicio.triage_incident("INC-1001", "a" * 10_001)

    assert excinfo.value.code == TRIAGE_TEXTO_DEMASIADO_LARGO


def test_texto_con_espacios_alrededor_es_valido(servicio: IncidentService) -> None:
    resultado = servicio.triage_incident("INC-1001", "  el botón cambió de color  ")

    assert resultado.severity == "P3"
