"""Política de SLA y resumen de incidentes activos (ADR-002, H002).

Migrado de `src/sla_calculator.py`: sin `print`, sin estado global mutable y con
la misma aritmética de ventana hábil. El escalamiento exige estado activo y el
incumplimiento es estrictamente `elapsed > allowed`.
"""

from datetime import datetime, time, timedelta
from types import MappingProxyType
from typing import Mapping, Sequence, Tuple

from src.domain.models import (
    ACTIVE_STATUSES,
    SEVERITY_INDEX,
    ActiveIncidentDetail,
    ActiveIncidentsSummary,
    Incident,
    SLAEvaluation,
    SLARule,
    SeverityLevel,
    TemporalInconsistencyError,
)

# 24x7 para P0/P1; lunes a viernes 08:00-18:00 para P2/P3.
SLA_POLICY_TABLE: Mapping[SeverityLevel, SLARule] = MappingProxyType(
    {
        "P0": SLARule(severity="P0", max_resolution_minutes=60, operates_24x7=True),
        "P1": SLARule(severity="P1", max_resolution_minutes=240, operates_24x7=True),
        "P2": SLARule(severity="P2", max_resolution_minutes=480, operates_24x7=False),
        "P3": SLARule(severity="P3", max_resolution_minutes=1440, operates_24x7=False),
    }
)

HORARIO_INICIO = time(8, 0)
HORARIO_FIN = time(18, 0)


def _validar_naive(instante: datetime, campo: str) -> None:
    """Rechaza fechas con zona horaria: el dominio solo admite instantes naive."""
    if instante.tzinfo is not None and instante.tzinfo.utcoffset(instante) is not None:
        raise TemporalInconsistencyError(
            f"El campo {campo} debe ser una fecha naive sin zona horaria."
        )


def get_sla_rule_for_severity(severity: SeverityLevel) -> SLARule:
    """Obtiene la regla de SLA aplicable a una severidad validada contra la tabla."""
    try:
        return SLA_POLICY_TABLE[severity]
    except KeyError as exc:
        raise TemporalInconsistencyError(
            f"Severidad no válida o sin política vigente: {severity}"
        ) from exc


def _minutos_habiles(created_at: datetime, end_time: datetime) -> int:
    """Acumula solo los bloques de lunes a viernes dentro de 08:00-18:00."""
    total_seconds = 0.0
    current_date = created_at.date()
    end_date = end_time.date()

    while current_date <= end_date:
        # 0 = lunes, ..., 4 = viernes. Festivos: deuda documentada (ADR-002).
        if current_date.weekday() < 5:
            work_start = datetime.combine(current_date, HORARIO_INICIO)
            work_end = datetime.combine(current_date, HORARIO_FIN)
            effective_start = max(created_at, work_start)
            effective_end = min(end_time, work_end)
            if effective_end > effective_start:
                total_seconds += (effective_end - effective_start).total_seconds()
        current_date += timedelta(days=1)

    return int(total_seconds // 60)


def evaluate_sla_status(incident: Incident, reference_time: datetime) -> SLAEvaluation:
    """Evalúa si un incidente incumplió su SLA o requiere escalamiento preventivo.

    Args:
        incident: Entidad del incidente a evaluar.
        reference_time: Instante único contra el cual medir los activos.

    Returns:
        La evaluación con minutos transcurridos, restantes y banderas de estado.
    """
    _validar_naive(incident.created_at, "created_at")
    _validar_naive(reference_time, "reference_time")
    if incident.resolved_at is not None:
        _validar_naive(incident.resolved_at, "resolved_at")

    rule = get_sla_rule_for_severity(incident.severity)
    end_time = incident.resolved_at or reference_time

    if end_time < incident.created_at:
        raise TemporalInconsistencyError(
            f"El instante de referencia {end_time.isoformat()} es anterior a la creación "
            f"del incidente {incident.incident_id} ({incident.created_at.isoformat()})."
        )

    if rule.operates_24x7:
        elapsed_minutes = int((end_time - incident.created_at).total_seconds() // 60)
    else:
        elapsed_minutes = _minutos_habiles(incident.created_at, end_time)

    remaining_minutes = rule.max_resolution_minutes - elapsed_minutes
    is_breached = elapsed_minutes > rule.max_resolution_minutes

    escalation_limit = int(rule.max_resolution_minutes * rule.escalation_threshold_ratio)
    requires_escalation = (
        incident.status in ACTIVE_STATUSES
        and not is_breached
        and elapsed_minutes >= escalation_limit
    )

    return SLAEvaluation(
        incident_id=incident.incident_id,
        severity=incident.severity,
        elapsed_minutes=elapsed_minutes,
        allowed_minutes=rule.max_resolution_minutes,
        remaining_minutes=remaining_minutes,
        is_breached=is_breached,
        requires_escalation=requires_escalation,
    )


def _clave_de_orden(detalle: ActiveIncidentDetail) -> Tuple[int, int, str]:
    """P0→P3, luego minutos descendentes y, en empate, identificador ascendente."""
    return (
        SEVERITY_INDEX[detalle.incident.severity],
        -detalle.evaluation.elapsed_minutes,
        detalle.incident.incident_id,
    )


def summarize_active_incidents(
    incidents: Sequence[Incident], reference_time: datetime
) -> ActiveIncidentsSummary:
    """Construye el resumen ordenado de los incidentes activos.

    Un incidente creado después del instante de referencia aborta la evaluación
    completa (FR-019); los estados terminales se excluyen aunque su SLA esté
    vencido (FR-002).
    """
    _validar_naive(reference_time, "reference_time")

    detalles = []
    for incident in incidents:
        _validar_naive(incident.created_at, "created_at")
        if incident.created_at > reference_time:
            raise TemporalInconsistencyError(
                f"El incidente {incident.incident_id} fue creado después del instante "
                f"de referencia ({incident.created_at.isoformat()} > "
                f"{reference_time.isoformat()})."
            )
        if incident.status not in ACTIVE_STATUSES:
            continue
        detalles.append(
            ActiveIncidentDetail(
                incident=incident,
                evaluation=evaluate_sla_status(incident, reference_time),
            )
        )

    detalles.sort(key=_clave_de_orden)

    return ActiveIncidentsSummary(
        total_active=len(detalles),
        breached_count=sum(1 for detalle in detalles if detalle.evaluation.is_breached),
        incidents=tuple(detalles),
    )
