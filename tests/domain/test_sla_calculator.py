"""Fronteras de SLA y resumen de activos (ADR-002, H002).

Tabla de casos de `data-model.md` §6. El instante de referencia siempre se
inyecta: no se usa `datetime.now()` ni `sleep`.
"""

from datetime import datetime, timedelta
from typing import Optional

import pytest

from src.domain.models import (
    Incident,
    IncidentStatus,
    InvalidIncidentError,
    SeverityLevel,
    TemporalInconsistencyError,
)
from src.domain.sla_calculator import (
    SLA_POLICY_TABLE,
    evaluate_sla_detail,
    evaluate_sla_status,
    get_sla_rule_for_severity,
    resolver_ventana_temporal,
    summarize_active_incidents,
    validar_instante_naive,
)

# 2026-11-16 es lunes: todas las fronteras hábiles caben en la ventana 08:00-18:00.
LUNES = datetime(2026, 11, 16, 8, 0, 0)


def _incidente(
    severity: SeverityLevel = "P0",
    status: IncidentStatus = "OPEN",
    created_at: datetime = LUNES,
    incident_id: str = "INC-1",
    resolved_at: Optional[datetime] = None,
) -> Incident:
    """Construye un incidente de dominio con valores por defecto deterministas."""
    return Incident(
        incident_id=incident_id,
        title=f"Incidente {incident_id}",
        component="payments-gateway",
        severity=severity,
        status=status,
        created_at=created_at,
        resolved_at=resolved_at,
    )


@pytest.mark.parametrize(
    ("severity", "minutos", "incumplido", "escala"),
    [
        ("P0", 44, False, False),
        ("P0", 45, False, True),
        ("P0", 46, False, True),
        ("P0", 60, False, True),
        ("P0", 61, True, False),
        ("P2", 359, False, False),
        ("P2", 360, False, True),
        ("P2", 361, False, True),
        ("P2", 479, False, True),
        ("P2", 480, False, True),
        ("P2", 481, True, False),
    ],
)
def test_fronteras_de_incumplimiento_y_escalamiento(
    severity: SeverityLevel, minutos: int, incumplido: bool, escala: bool
) -> None:
    """SC-005: un minuto antes, en el límite y un minuto después del máximo."""
    referencia = LUNES + timedelta(minutes=minutos)

    evaluacion = evaluate_sla_status(_incidente(severity=severity), referencia)

    permitido = SLA_POLICY_TABLE[severity].max_resolution_minutes
    assert evaluacion.elapsed_minutes == minutos
    assert evaluacion.allowed_minutes == permitido
    assert evaluacion.remaining_minutes == permitido - minutos
    assert evaluacion.is_breached is incumplido
    assert evaluacion.requires_escalation is escala


def test_p2_creado_el_viernes_no_acumula_el_fin_de_semana() -> None:
    """Viernes 17:00 → lunes 09:00 son 120 minutos hábiles, no 3.840."""
    viernes = datetime(2026, 11, 20, 17, 0, 0)
    lunes = datetime(2026, 11, 23, 9, 0, 0)

    evaluacion = evaluate_sla_status(_incidente(severity="P2", created_at=viernes), lunes)

    assert evaluacion.elapsed_minutes == 120
    assert evaluacion.is_breached is False
    assert evaluacion.requires_escalation is False


def test_escalamiento_exacto_al_setenta_y_cinco_por_ciento() -> None:
    """P2 con 360 minutos alcanza exactamente el 75 % de 480 y debe escalar."""
    evaluacion = evaluate_sla_status(
        _incidente(severity="P2"), LUNES + timedelta(minutes=360)
    )

    assert evaluacion.requires_escalation is True
    assert evaluacion.is_breached is False


def test_incumplimiento_desactiva_el_escalamiento() -> None:
    """Un incidente ya incumplido no se marca como escalamiento pendiente."""
    evaluacion = evaluate_sla_status(
        _incidente(severity="P0"), LUNES + timedelta(minutes=61)
    )

    assert evaluacion.is_breached is True
    assert evaluacion.requires_escalation is False


def test_terminal_evaluado_usa_resolved_at_y_no_escala() -> None:
    """RESOLVED mide contra su resolución y nunca requiere escalamiento."""
    resuelto = _incidente(
        severity="P0",
        status="RESOLVED",
        resolved_at=LUNES + timedelta(minutes=30),
    )

    evaluacion = evaluate_sla_status(resuelto, LUNES + timedelta(days=1))

    assert evaluacion.elapsed_minutes == 30
    assert evaluacion.is_breached is False
    assert evaluacion.requires_escalation is False


def test_cerrado_no_escala_aunque_alcanzara_el_umbral() -> None:
    """La regla corrige el legado: CLOSED tampoco escala."""
    cerrado = _incidente(
        severity="P2",
        status="CLOSED",
        resolved_at=LUNES + timedelta(minutes=360),
    )

    evaluacion = evaluate_sla_status(cerrado, LUNES + timedelta(minutes=360))

    assert evaluacion.requires_escalation is False


def test_resumen_excluye_terminales_aunque_su_sla_este_vencido() -> None:
    """FR-002: RESOLVED y CLOSED quedan fuera del resumen."""
    activo = _incidente("P0", "OPEN", LUNES, "INC-1")
    resuelto = _incidente(
        "P0", "RESOLVED", LUNES, "INC-2", resolved_at=LUNES + timedelta(hours=3)
    )
    cerrado = _incidente(
        "P0", "CLOSED", LUNES, "INC-3", resolved_at=LUNES + timedelta(hours=4)
    )

    resumen = summarize_active_incidents(
        [activo, resuelto, cerrado], LUNES + timedelta(minutes=10)
    )

    assert resumen.total_active == 1
    assert resumen.breached_count == 0
    assert [detalle.incident.incident_id for detalle in resumen.incidents] == ["INC-1"]


def test_incidente_creado_despues_del_instante_aborta_el_resumen() -> None:
    """FR-019: la incoherencia temporal rechaza el resumen completo."""
    creado = datetime(2026, 11, 16, 12, 0, 0)
    referencia = datetime(2026, 11, 16, 11, 59, 0)

    with pytest.raises(TemporalInconsistencyError):
        summarize_active_incidents([_incidente(created_at=creado)], referencia)


def test_resumen_ordena_por_severidad_minutos_e_identificador() -> None:
    """FR-012: P0→P3, minutos descendentes y, en empate, identificador ascendente."""
    referencia = LUNES + timedelta(hours=10)
    incidentes = [
        _incidente("P3", created_at=LUNES, incident_id="INC-9"),
        _incidente("P0", created_at=LUNES, incident_id="INC-2"),
        _incidente("P0", created_at=LUNES + timedelta(minutes=100), incident_id="INC-1"),
        _incidente("P1", created_at=LUNES, incident_id="INC-3"),
        _incidente("P0", created_at=LUNES + timedelta(minutes=100), incident_id="INC-0"),
    ]

    resumen = summarize_active_incidents(incidentes, referencia)

    assert [detalle.incident.incident_id for detalle in resumen.incidents] == [
        "INC-2",
        "INC-0",
        "INC-1",
        "INC-3",
        "INC-9",
    ]


def test_totales_del_resumen_coinciden_con_el_detalle() -> None:
    """Invariantes 1 y 2 del modelo: total y conteo de incumplidos."""
    referencia = LUNES + timedelta(hours=2)
    incidentes = [
        _incidente("P0", created_at=LUNES, incident_id="INC-1"),
        _incidente("P0", created_at=LUNES + timedelta(minutes=90), incident_id="INC-2"),
        _incidente("P2", created_at=LUNES, incident_id="INC-3"),
    ]

    resumen = summarize_active_incidents(incidentes, referencia)

    assert resumen.total_active == len(resumen.incidents)
    assert resumen.breached_count == sum(
        1 for detalle in resumen.incidents if detalle.evaluation.is_breached
    )
    assert resumen.breached_count == 1


def test_tabla_de_politicas_es_inmutable() -> None:
    """La política es una constante del dominio, no estado global mutable."""
    with pytest.raises(TypeError):
        SLA_POLICY_TABLE["P0"] = SLA_POLICY_TABLE["P1"]  # type: ignore[index]


def test_severidad_fuera_de_la_politica_es_rechazada() -> None:
    with pytest.raises(ValueError):
        get_sla_rule_for_severity("P9")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# H003 · Normalización temporal y evaluación con contexto
# ---------------------------------------------------------------------------


def test_validar_instante_naive_acepta_naive_y_rechaza_aware() -> None:
    """FR-024: la normalización única rechaza la zona horaria, no la convierte."""
    validar_instante_naive(LUNES, "created_at")

    with pytest.raises(TemporalInconsistencyError):
        validar_instante_naive(LUNES.astimezone(), "created_at")


@pytest.mark.parametrize(
    ("incidente", "campo"),
    [
        (_incidente(created_at=LUNES.astimezone()), "created_at"),
        (
            _incidente(
                status="RESOLVED",
                resolved_at=(LUNES + timedelta(minutes=5)).astimezone(),
            ),
            "resolved_at",
        ),
    ],
)
def test_evaluate_sla_detail_rechaza_aware_en_los_tres_campos(
    incidente: Incident, campo: str
) -> None:
    """Los tres instantes del cómputo deben ser naive."""
    with pytest.raises(TemporalInconsistencyError):
        evaluate_sla_detail(incidente, LUNES + timedelta(minutes=10))

    with pytest.raises(TemporalInconsistencyError):
        evaluate_sla_detail(_incidente(), (LUNES + timedelta(minutes=10)).astimezone())


def test_resolver_ventana_temporal_deriva_la_ventana_de_la_politica() -> None:
    """FR-018: 24x7 para P0/P1 y hábil para P2/P3, sin mirar el adaptador."""
    _, fin_p0, ventana_p0 = resolver_ventana_temporal(
        _incidente(severity="P0"), LUNES + timedelta(minutes=30)
    )
    _, fin_p2, ventana_p2 = resolver_ventana_temporal(
        _incidente(severity="P2"), LUNES + timedelta(minutes=30)
    )

    assert fin_p0 == LUNES + timedelta(minutes=30)
    assert fin_p2 == LUNES + timedelta(minutes=30)
    assert ventana_p0 == "24x7"
    assert ventana_p2 == "BUSINESS_HOURS"


def test_resolver_ventana_congela_el_fin_en_resolved_at() -> None:
    """FR-026: en terminales el fin del cómputo es la resolución."""
    resolucion = LUNES + timedelta(minutes=20)
    terminal = _incidente(status="RESOLVED", resolved_at=resolucion)

    _, fin, ventana = resolver_ventana_temporal(
        terminal, LUNES + timedelta(days=1)
    )

    assert fin == resolucion
    assert ventana == "24x7"


def test_referencia_anterior_a_la_creacion_se_rechaza_tambien_en_terminales() -> None:
    """FR-022: la referencia nunca precede a la creación, ni en un terminal."""
    terminal = _incidente(
        status="RESOLVED", resolved_at=LUNES + timedelta(minutes=30)
    )

    with pytest.raises(TemporalInconsistencyError):
        resolver_ventana_temporal(terminal, LUNES - timedelta(minutes=1))


def test_terminal_sin_resolved_at_es_dato_incoherente() -> None:
    """FR-031: un terminal sin resolución es incoherencia de datos."""
    with pytest.raises(InvalidIncidentError):
        resolver_ventana_temporal(
            _incidente(status="CLOSED"), LUNES + timedelta(minutes=5)
        )


def test_resolved_at_anterior_a_created_at_es_dato_incoherente() -> None:
    """FR-031: la resolución no puede preceder a la creación."""
    with pytest.raises(InvalidIncidentError):
        resolver_ventana_temporal(
            _incidente(
                status="RESOLVED", resolved_at=LUNES - timedelta(minutes=1)
            ),
            LUNES + timedelta(minutes=5),
        )


def test_severidad_desconocida_es_dato_incoherente_en_la_auditoria() -> None:
    """FR-031: sin política vigente no se inventan valores por defecto."""
    with pytest.raises(InvalidIncidentError):
        resolver_ventana_temporal(
            _incidente(severity="P9"), LUNES + timedelta(minutes=5)  # type: ignore[arg-type]
        )


def test_evaluate_sla_detail_conserva_los_valores_de_h002() -> None:
    """El cálculo de H002 no cambia: solo se le adjunta el contexto."""
    referencia = LUNES + timedelta(minutes=61)
    incidente = _incidente(severity="P0")

    detalle = evaluate_sla_detail(incidente, referencia)

    assert detalle.evaluation == evaluate_sla_status(incidente, referencia)
    assert detalle.incident == incidente
    assert detalle.reference_time == referencia
    assert detalle.window == "24x7"
    assert detalle.evaluation.is_breached is True


def test_evaluate_sla_detail_p2_viernes_a_lunes() -> None:
    """FR-018: la ventana hábil se informa y excluye el fin de semana."""
    viernes = datetime(2026, 11, 20, 17, 0, 0)
    lunes = datetime(2026, 11, 23, 9, 0, 0)

    detalle = evaluate_sla_detail(
        _incidente(severity="P2", created_at=viernes), lunes
    )

    assert detalle.window == "BUSINESS_HOURS"
    assert detalle.evaluation.elapsed_minutes == 120
    assert detalle.evaluation.allowed_minutes == 480


@pytest.mark.parametrize(
    "referencia",
    [
        datetime(2026, 11, 16, 8, 10, 0),
        datetime(2026, 11, 16, 9, 0, 0),
    ],
)
def test_terminal_congelado_antes_y_despues_de_la_resolucion(
    referencia: datetime,
) -> None:
    """FR-026: el reloj de SLA no retrocede ni crece tras la resolución."""
    terminal = _incidente(
        status="RESOLVED", resolved_at=LUNES + timedelta(minutes=10)
    )

    detalle = evaluate_sla_detail(terminal, referencia)

    assert detalle.evaluation.elapsed_minutes == 10
    assert detalle.evaluation.requires_escalation is False


def test_referencia_igual_a_la_creacion_da_cero() -> None:
    """Caso límite: cero minutos, sin incumplimiento ni escalamiento."""
    detalle = evaluate_sla_detail(_incidente(), LUNES)

    assert detalle.evaluation.elapsed_minutes == 0
    assert detalle.evaluation.is_breached is False
    assert detalle.evaluation.requires_escalation is False
