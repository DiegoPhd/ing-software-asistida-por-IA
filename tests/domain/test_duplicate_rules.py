"""Reglas puras de equivalencia y aviso de duplicados (Constitución §1.4).

Tabla de casos de `data-model.md` §4: umbral exacto, ventana de la severidad
del más antiguo, candidato terminal, otro componente, texto ausente, candidato
posterior y herencia de la clave del original. El tiempo siempre se inyecta.
"""

from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import List, Optional

import pytest

from src.domain.models import Incident, IncidentStatus, SeverityLevel
from src.domain.triage_rules import (
    DUPLICATE_SIMILARITY_THRESHOLD,
    DUPLICATE_WINDOW_DAYS,
    DuplicateAssessment,
    assess_duplicates,
    is_equivalent,
)

BASE = datetime(2026, 11, 20, 10, 0, 0)
TEXTO = "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta."


def _incidente(
    incident_id: str,
    created_at: datetime = BASE,
    component: str = "payments-gateway",
    severity: SeverityLevel = "P0",
    status: IncidentStatus = "OPEN",
    raw_text: Optional[str] = TEXTO,
    duplicate_group_key: Optional[str] = None,
) -> Incident:
    return Incident(
        incident_id=incident_id,
        title=f"Incidente {incident_id}",
        component=component,
        severity=severity,
        status=status,
        created_at=created_at,
        raw_text=raw_text,
        duplicate_group_key=duplicate_group_key,
    )


def test_umbral_exacto_de_similitud_es_equivalente() -> None:
    """La frontera exacta de 0,75 cuenta; un valor menor no."""
    assert SequenceMatcher(None, "abcd", "abce").ratio() == DUPLICATE_SIMILARITY_THRESHOLD

    equivalente = _incidente("INC-1", raw_text="abcd")
    nuevo = _incidente("INC-2", raw_text="abce")

    assert is_equivalent(equivalente, nuevo) is True


def test_similitud_de_0_74_no_es_equivalente() -> None:
    """FR-011: un valor inmediatamente inferior a 0,75 no es equivalente."""
    primer_texto = "a" * 37 + "b" * 13
    segundo_texto = "a" * 37 + "c" * 13
    assert SequenceMatcher(None, primer_texto, segundo_texto).ratio() == 0.74

    assert (
        is_equivalent(
            _incidente("INC-1", raw_text=primer_texto),
            _incidente("INC-2", raw_text=segundo_texto),
        )
        is False
    )


def test_frontera_exacta_de_la_ventana_es_candidata() -> None:
    """El límite exacto de la ventana cuenta; un segundo más lo excluye."""
    un_dia = timedelta(days=DUPLICATE_WINDOW_DAYS["P0"])
    antiguo = _incidente("INC-1", created_at=BASE)

    assert is_equivalent(antiguo, _incidente("INC-2", created_at=BASE + un_dia)) is True
    assert (
        is_equivalent(
            antiguo, _incidente("INC-2", created_at=BASE + un_dia + timedelta(seconds=1))
        )
        is False
    )


@pytest.mark.parametrize(
    ("severity_antiguo", "dias", "esperado"),
    [
        ("P0", 1, True),
        ("P0", 2, False),
        ("P1", 2, True),
        ("P1", 3, False),
        ("P2", 3, True),
        ("P2", 4, False),
        ("P3", 4, True),
        ("P3", 5, False),
    ],
)
def test_la_ventana_la_fija_el_mas_antiguo_del_par(
    severity_antiguo: SeverityLevel, dias: int, esperado: bool
) -> None:
    """SC-002: la ventana depende de la severidad del incidente más antiguo."""
    antiguo = _incidente(
        "INC-1", created_at=BASE, severity=severity_antiguo
    )
    nuevo = _incidente(
        "INC-2", created_at=BASE + timedelta(days=dias), severity="P0"
    )

    assert is_equivalent(antiguo, nuevo) is esperado


@pytest.mark.parametrize("status", ["RESOLVED", "CLOSED"])
def test_un_candidato_terminal_nunca_es_equivalente(status: IncidentStatus) -> None:
    """US2 escenario 2: los terminales quedan fuera de la comparación."""
    terminal = _incidente(
        "INC-1", status=status, created_at=BASE
    )
    terminal = Incident(
        incident_id=terminal.incident_id,
        title=terminal.title,
        component=terminal.component,
        severity=terminal.severity,
        status=terminal.status,
        created_at=terminal.created_at,
        resolved_at=BASE + timedelta(minutes=30),
        raw_text=terminal.raw_text,
    )

    assert is_equivalent(terminal, _incidente("INC-2")) is False


def test_otro_componente_no_es_equivalente() -> None:
    """US2 escenario 3: sólo se compara dentro del mismo componente."""
    assert (
        is_equivalent(
            _incidente("INC-1", component="auth-identity"),
            _incidente("INC-2", component="payments-gateway"),
        )
        is False
    )


@pytest.mark.parametrize("texto", [None, "", "   "])
def test_un_candidato_sin_texto_no_es_equivalente(texto: Optional[str]) -> None:
    """US2 caso límite: sin texto original no hay comparación posible."""
    assert (
        is_equivalent(
            _incidente("INC-1", raw_text=texto),
            _incidente("INC-2", raw_text=TEXTO),
        )
        is False
    )


def test_el_mismo_identificador_no_es_equivalente() -> None:
    """Un incidente no se compara consigo mismo."""
    assert is_equivalent(_incidente("INC-1"), _incidente("INC-1")) is False


def test_assess_sin_previos_devuelve_aviso_vacio() -> None:
    """Sin equivalentes previos, la clave es nula y la lista vacía."""
    evaluacion = assess_duplicates(_incidente("INC-2"), [])

    assert evaluacion == DuplicateAssessment(None, ())
    assert evaluacion.is_duplicate is False


def test_assess_ignora_equivalentes_posteriores() -> None:
    """Sólo informa duplicados previos: un equivalente futuro no cuenta."""
    nuevo = _incidente("INC-2", created_at=BASE)
    futuro = _incidente("INC-3", created_at=BASE + timedelta(minutes=5))

    assert assess_duplicates(nuevo, [futuro]) == DuplicateAssessment(None, ())
    assert is_equivalent(futuro, nuevo) is True


def test_assess_informa_el_previo_ordenado_y_con_su_clave() -> None:
    """`duplicate_of` se ordena por (created_at, incident_id) ascendente."""
    nuevo = _incidente("INC-9", created_at=BASE + timedelta(hours=1))
    candidatos: List[Incident] = [
        _incidente("INC-2", created_at=BASE + timedelta(minutes=10)),
        _incidente("INC-1", created_at=BASE),
    ]

    evaluacion = assess_duplicates(nuevo, candidatos)

    assert evaluacion.duplicate_of == ("INC-1", "INC-2")
    assert evaluacion.duplicate_group_key == "INC-1"
    assert evaluacion.is_duplicate is True


def test_assess_hereda_la_clave_del_original() -> None:
    """FR-014: la clave es la del original, nunca la de un duplicado intermedio."""
    nuevo = _incidente("INC-9", created_at=BASE + timedelta(hours=2))
    original = _incidente("INC-1", created_at=BASE, duplicate_group_key="INC-0")
    intermedio = _incidente(
        "INC-2",
        created_at=BASE + timedelta(minutes=30),
        duplicate_group_key="INC-0",
    )

    evaluacion = assess_duplicates(nuevo, [intermedio, original])

    assert evaluacion.duplicate_group_key == "INC-0"
    assert evaluacion.duplicate_of == ("INC-1", "INC-2")


def test_el_mas_antiguo_no_hereda_clave_y_no_reescribe_previos() -> None:
    """US2 caso límite: el nuevo más antiguo es el original del grupo."""
    nuevo = _incidente("INC-0", created_at=BASE)
    posterior = _incidente(
        "INC-1",
        created_at=BASE + timedelta(minutes=1),
        duplicate_group_key=None,
    )

    evaluacion = assess_duplicates(nuevo, [posterior])

    assert evaluacion == DuplicateAssessment(None, ())
    assert posterior.duplicate_group_key is None


def test_assess_descarta_terminales_de_otro_componente_y_sin_texto() -> None:
    """SC-002: ninguna de esas variantes produce un falso aviso."""
    nuevo = _incidente("INC-9", created_at=BASE + timedelta(hours=1))
    candidatos = [
        _incidente("INC-T", status="CLOSED", created_at=BASE),
        _incidente("INC-C", component="auth-identity", created_at=BASE),
        _incidente("INC-N", raw_text=None, created_at=BASE),
    ]

    assert assess_duplicates(nuevo, candidatos) == DuplicateAssessment(None, ())


def test_la_tabla_de_ventanas_es_inmutable() -> None:
    """La ventana por severidad es una constante del dominio."""
    with pytest.raises(TypeError):
        DUPLICATE_WINDOW_DAYS["P0"] = 99  # type: ignore[index]
