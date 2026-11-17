from datetime import datetime, time, timedelta
from typing import Dict, Literal, Optional

# Tipos base definidos en src/models.py
SeverityLevel = Literal["P0", "P1", "P2", "P3"]
IncidentStatus = Literal["OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED"]


class SLARule:
    """Define el acuerdo de nivel de servicio (SLA) para un nivel de severidad."""
    def __init__(
        self,
        severity: SeverityLevel,
        max_resolution_minutes: int,
        operates_24x7: bool,
        escalation_threshold_ratio: float = 0.75,
    ):
        self.severity = severity
        self.max_resolution_minutes = max_resolution_minutes
        self.operates_24x7 = operates_24x7
        self.escalation_threshold_ratio = escalation_threshold_ratio


class Incident:
    """Representa un incidente registrado en la plataforma IncidentOps."""
    def __init__(
        self,
        incident_id: str,
        title: str,
        component: str,
        severity: SeverityLevel,
        status: IncidentStatus,
        created_at: datetime,
        resolved_at: Optional[datetime] = None,
        raw_text: Optional[str] = None,
    ):
        self.incident_id = incident_id
        self.title = title
        self.component = component
        self.severity = severity
        self.status = status
        self.created_at = created_at
        self.resolved_at = resolved_at
        self.raw_text = raw_text


class SLAEvaluation:
    """Resultado determinista de la evaluación de SLA de un incidente."""
    def __init__(
        self,
        incident_id: str,
        severity: SeverityLevel,
        elapsed_minutes: int,
        allowed_minutes: int,
        remaining_minutes: int,
        is_breached: bool,
        requires_escalation: bool,
    ):
        self.incident_id = incident_id
        self.severity = severity
        self.elapsed_minutes = elapsed_minutes
        self.allowed_minutes = allowed_minutes
        self.remaining_minutes = remaining_minutes
        self.is_breached = is_breached
        self.requires_escalation = requires_escalation

    def __repr__(self) -> str:
        return (
            f"SLAEvaluation(id={self.incident_id}, severity={self.severity}, "
            f"elapsed={self.elapsed_minutes}m, allowed={self.allowed_minutes}m, "
            f"remaining={self.remaining_minutes}m, breached={self.is_breached}, "
            f"escalation={self.requires_escalation})"
        )


SLA_POLICY_TABLE: Dict[SeverityLevel, SLARule] = {
    "P0": SLARule(severity="P0", max_resolution_minutes=60, operates_24x7=True),
    "P1": SLARule(severity="P1", max_resolution_minutes=240, operates_24x7=True),
    "P2": SLARule(severity="P2", max_resolution_minutes=480, operates_24x7=False),
    "P3": SLARule(severity="P3", max_resolution_minutes=1440, operates_24x7=False),
}


def get_sla_rule_for_severity(severity: SeverityLevel) -> SLARule:
    """Obtiene la regla de SLA aplicable a una severidad validada contra la tabla."""
    if severity not in SLA_POLICY_TABLE:
        raise ValueError(f"Severidad no válida: {severity}")
    return SLA_POLICY_TABLE[severity]


def evaluate_sla_status(incident: Incident, reference_time: datetime) -> SLAEvaluation:
    """Evalúa si un incidente ha incumplido su SLA o requiere escalamiento preventivo.

    Args:
        incident: Entidad del incidente a evaluar.
        reference_time: Marca de tiempo actual o de cierre contra la cual medir.

    Returns:
        SLAEvaluation con los minutos transcurridos, restantes y banderas de estado.
    """
    rule = get_sla_rule_for_severity(incident.severity)
    end_time = incident.resolved_at or reference_time

    if end_time < incident.created_at:
        raise ValueError("El tiempo de referencia no puede ser anterior a la creación.")

    # 1. Bifurcación por modalidad de operación
    if rule.operates_24x7:
        delta_seconds = (end_time - incident.created_at).total_seconds()
        elapsed_minutes = int(delta_seconds // 60)
    else:
        # 2. Cálculo por bloques de días con intersección de ventana laboral (08:00 - 18:00)
        total_seconds = 0.0
        current_date = incident.created_at.date()
        end_date = end_time.date()

        while current_date <= end_date:
            # Filtrar fines de semana (0 = Lunes, ..., 5 = Sábado, 6 = Domingo)
            if current_date.weekday() < 5:
                # TODO(week-1-taller): Integrar calendario de días festivos locales
                work_start = datetime.combine(current_date, time(8, 0))
                work_end = datetime.combine(current_date, time(18, 0))

                effective_start = max(incident.created_at, work_start)
                effective_end = min(end_time, work_end)

                if effective_end > effective_start:
                    total_seconds += (effective_end - effective_start).total_seconds()

            current_date += timedelta(days=1)

        elapsed_minutes = int(total_seconds // 60)

    # 3. Evaluación de umbrales y estado de cumplimiento
    remaining_minutes = rule.max_resolution_minutes - elapsed_minutes
    is_breached = elapsed_minutes > rule.max_resolution_minutes

    escalation_limit = int(rule.max_resolution_minutes * rule.escalation_threshold_ratio)
    requires_escalation = (
        incident.status != "RESOLVED"
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


def main() -> None:
    """Función de demostración con diversos casos de prueba y casos borde."""
    print("=== DEMO: EVALUACIÓN DE SLA EN INCIDENTOPS (ADR-002) ===\n")

    # Caso 1: Incidente P0 (24x7) creado y evaluado 30 minutos después
    inc_p0 = Incident(
        incident_id="INC-001",
        title="Fallo crítico en pasarela de pagos",
        component="payments",
        severity="P0",
        status="OPEN",
        created_at=datetime(2026, 11, 16, 2, 0, 0),
    )
    eval_p0 = evaluate_sla_status(inc_p0, reference_time=datetime(2026, 11, 16, 2, 30, 0))
    print(f"Caso 1 [P0 24x7]: {eval_p0}")

    # Caso 2: Incidente P2 creado un viernes a las 17:00 y evaluado el lunes a las 09:00
    # Horas hábiles esperadas: Viernes 17:00-18:00 (60m) + Lunes 08:00-09:00 (60m) = 120 minutos totales
    inc_p2_weekend = Incident(
        incident_id="INC-002",
        title="Lentitud en reporte analítico",
        component="analytics",
        severity="P2",
        status="OPEN",
        created_at=datetime(2026, 11, 13, 17, 0, 0),  # Viernes
    )
    eval_p2_weekend = evaluate_sla_status(
        inc_p2_weekend, reference_time=datetime(2026, 11, 16, 9, 0, 0)  # Lunes
    )
    print(f"Caso 2 [P2 Fin de Semana - 120m esperados]: {eval_p2_weekend}")

    # Caso 3: Incidente P2 creado un sábado (fuera de horario) y evaluado el lunes a las 08:30
    # Horas hábiles esperadas: Sábado/Domingo (0m) + Lunes 08:00-08:30 (30m) = 30 minutos totales
    inc_p2_sat = Incident(
        incident_id="INC-003",
        title="Alerta menor de almacenamiento",
        component="storage",
        severity="P2",
        status="OPEN",
        created_at=datetime(2026, 11, 14, 14, 0, 0),  # Sábado
    )
    eval_p2_sat = evaluate_sla_status(
        inc_p2_sat, reference_time=datetime(2026, 11, 16, 8, 30, 0)  # Lunes
    )
    print(f"Caso 3 [P2 Creado en Sábado - 30m esperados]: {eval_p2_sat}")

    # Caso 4: Incidente P2 alcanzando el umbral de escalamiento preventivo (75% de 480 min = 360 min)
    inc_p2_esc = Incident(
        incident_id="INC-004",
        title="Error intermitente de caché",
        component="cache",
        severity="P2",
        status="IN_PROGRESS",
        created_at=datetime(2026, 11, 9, 9, 0, 0),  # Lunes anterior
    )
    # 360 minutos efectivos de trabajo equivalen exactamente a 6 horas hábiles
    eval_p2_esc = evaluate_sla_status(
        inc_p2_esc, reference_time=datetime(2026, 11, 9, 15, 0, 0)
    )
    print(f"Caso 4 [P2 Escalamiento Preventivo (360m)]: {eval_p2_esc}")
    
    # Caso 5: Incidente P3 creado de noche fuera de horario (21:00) y evaluado al día siguiente a las 10:00
    # Horas hábiles esperadas: Noche anterior (0m) + Mañana siguiente de 08:00 a 10:00 (120m) = 120 minutos totales
    inc_p3_night = Incident(
        incident_id="INC-005",
        title="Advertencia menor de respaldo nocturno",
        component="backup",
        severity="P3",
        status="OPEN",
        created_at=datetime(2026, 11, 16, 21, 0, 0),  # Lunes a las 21:00 (fuera de horario)
    )
    eval_p3_night = evaluate_sla_status(
        inc_p3_night, reference_time=datetime(2026, 11, 17, 10, 0, 0)  # Martes a las 10:00
    )
    print(f"Caso 5 [P3 Creado en Horario Nocturno - 120m esperados]: {eval_p3_night}")


if __name__ == "__main__":
    main()