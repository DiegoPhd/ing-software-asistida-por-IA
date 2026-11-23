"""Pruebas de los casos de uso de triaje, alta persistente y auditoría de SLA."""

from datetime import datetime, timedelta
from typing import List, Optional, Sequence

import pytest

from src.application.services import (
    CREATE_CREACION_INVALIDA,
    CREATE_ID_DEMASIADO_LARGO,
    CREATE_ID_VACIO,
    CREATE_TEXTO_DEMASIADO_LARGO,
    CREATE_TEXTO_VACIO,
    CREATE_TITULO_DEMASIADO_LARGO,
    CREATE_TITULO_VACIO,
    SLA_DATOS_INCONSISTENTES,
    SLA_ID_VACIO,
    SLA_REFERENCIA_INCONSISTENTE,
    SLA_REFERENCIA_INVALIDA,
    TRIAGE_ID_DEMASIADO_LARGO,
    TRIAGE_ID_VACIO,
    TRIAGE_TEXTO_DEMASIADO_LARGO,
    TRIAGE_TEXTO_VACIO,
    DataInconsistencyError,
    IncidentAlreadyExistsError,
    IncidentNotFoundError,
    IncidentService,
    ValidationError,
)
from src.domain.models import Incident

BASE = datetime(2026, 11, 20, 10, 0, 0)
TEXTO_P0 = (
    "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta."
)


class _RepositorioVacio:
    """Doble del puerto para las pruebas que solo ejercitan el triaje."""

    def save_incident(self, incident: Incident) -> None:
        return None

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        return None

    def find_open_duplicates(self, incident: Incident) -> Sequence[Incident]:
        return []

    def list_active_incidents(
        self, component_filter: Optional[str]
    ) -> Sequence[Incident]:
        return []

    def check_health(self) -> bool:
        return True


@pytest.fixture()
def servicio() -> IncidentService:
    return IncidentService(_RepositorioVacio())


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


# ---------------------------------------------------------------------------
# H003 · Dobles del puerto y del reloj
# ---------------------------------------------------------------------------


class _RelojFijo:
    """Doble de `ClockPort` que cuenta cuántas veces se lee."""

    def __init__(self, instante: datetime = BASE) -> None:
        self._instante = instante
        self.llamadas = 0

    def now(self) -> datetime:
        self.llamadas += 1
        return self._instante


class _RepositorioFalso:
    """Doble del puerto con conflicto, candidatos y contador de escrituras."""

    def __init__(self, incidentes: Sequence[Incident] = ()) -> None:
        self.incidentes: List[Incident] = list(incidentes)
        self.guardados: List[Incident] = []

    def save_incident(self, incident: Incident) -> None:
        if any(
            existente.incident_id == incident.incident_id
            for existente in self.incidentes
        ):
            raise IncidentAlreadyExistsError(incident.incident_id)
        self.incidentes.append(incident)
        self.guardados.append(incident)

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        return next(
            (
                incidente
                for incidente in self.incidentes
                if incidente.incident_id == incident_id
            ),
            None,
        )

    def find_open_duplicates(self, incident: Incident) -> Sequence[Incident]:
        return [
            otro
            for otro in self.incidentes
            if otro.status in ("OPEN", "IN_PROGRESS")
            and otro.component == incident.component
            and otro.incident_id != incident.incident_id
        ]

    def list_active_incidents(
        self, component_filter: Optional[str]
    ) -> Sequence[Incident]:
        return [
            incidente
            for incidente in self.incidentes
            if incidente.status in ("OPEN", "IN_PROGRESS")
            and (component_filter is None or incidente.component == component_filter)
        ]

    def check_health(self) -> bool:
        return True


def _incidente(
    incident_id: str = "INC-1",
    created_at: datetime = BASE,
    severity: str = "P0",
    status: str = "OPEN",
    resolved_at: Optional[datetime] = None,
    raw_text: Optional[str] = TEXTO_P0,
) -> Incident:
    return Incident(
        incident_id=incident_id,
        title=f"Incidente {incident_id}",
        component="payments-gateway",
        severity=severity,
        status=status,
        created_at=created_at,
        resolved_at=resolved_at,
        raw_text=raw_text,
    )


# ---------------------------------------------------------------------------
# US1 · Alta persistente
# ---------------------------------------------------------------------------


def test_el_alta_clasifica_persiste_y_lee_el_reloj_una_sola_vez() -> None:
    """FR-004/FR-005: clasificación canónica, estado OPEN y un único instante."""
    repositorio = _RepositorioFalso()
    reloj = _RelojFijo()
    servicio = IncidentService(repositorio, clock=reloj)

    resultado = servicio.create_incident("  INC-1001  ", TEXTO_P0)

    guardado = resultado.incident
    assert reloj.llamadas == 1
    assert guardado.incident_id == "INC-1001"
    assert guardado.component == "payments-gateway"
    assert guardado.severity == "P0"
    assert guardado.recommended_team == "Backend-Core"
    assert guardado.status == "OPEN"
    assert guardado.created_at == BASE
    assert guardado.resolved_at is None
    assert guardado.duplicate_group_key is None
    assert repositorio.guardados == [guardado]
    assert resultado.duplicate.is_duplicate is False
    assert resultado.duplicate.duplicate_of == ()


def test_el_titulo_se_deriva_de_la_primera_linea_sin_superar_200() -> None:
    """FR-007: título determinista de la primera línea, truncado a 200."""
    servicio = IncidentService(_RepositorioFalso(), clock=_RelojFijo())

    corto = servicio.create_incident("INC-1", "  Primera línea.\nSegunda línea.")
    largo = servicio.create_incident("INC-2", "L" * 500 + "\nresto")

    assert corto.incident.title == "Primera línea."
    assert largo.incident.title == "L" * 200


def test_el_titulo_indicado_se_recorta_y_se_valida() -> None:
    """FR-007: el título explícito se recorta y respeta el máximo."""
    servicio = IncidentService(_RepositorioFalso(), clock=_RelojFijo())

    resultado = servicio.create_incident("INC-1", TEXTO_P0, title="  Pagos caídos  ")

    assert resultado.incident.title == "Pagos caídos"


def test_el_texto_se_persiste_sin_normalizar() -> None:
    """FR-006: se recorta para validar, pero se guarda el original."""
    servicio = IncidentService(_RepositorioFalso(), clock=_RelojFijo())
    texto = "  Pasarela de pagos caída: ningún comercio puede cobrar.  "

    resultado = servicio.create_incident("INC-1", texto)

    assert resultado.incident.raw_text == texto


def test_created_at_explicito_no_lee_el_reloj() -> None:
    """FR-005: el instante indicado por el cliente se respeta y no se sustituye."""
    reloj = _RelojFijo(BASE + timedelta(hours=5))
    servicio = IncidentService(_RepositorioFalso(), clock=reloj)
    indicado = BASE - timedelta(days=1)

    resultado = servicio.create_incident("INC-1", TEXTO_P0, created_at=indicado)

    assert resultado.incident.created_at == indicado
    assert reloj.llamadas == 0


def test_el_conflicto_del_puerto_se_propaga_sin_sobrescribir() -> None:
    """FR-008: un identificador existente es conflicto, no reemplazo."""
    original = _incidente("INC-1")
    repositorio = _RepositorioFalso([original])
    servicio = IncidentService(repositorio, clock=_RelojFijo())

    with pytest.raises(IncidentAlreadyExistsError) as excinfo:
        servicio.create_incident("INC-1", "Otro texto distinto.")

    assert excinfo.value.code == "CREATE_ID_CONFLICTO"
    assert repositorio.guardados == []
    assert repositorio.get_incident("INC-1") == original


@pytest.mark.parametrize(
    ("kwargs", "codigo", "campo"),
    [
        ({"incident_id": "   ", "raw_text": TEXTO_P0}, CREATE_ID_VACIO, "incident_id"),
        ({"incident_id": "I" * 65, "raw_text": TEXTO_P0}, CREATE_ID_DEMASIADO_LARGO, "incident_id"),
        ({"incident_id": "INC-1", "raw_text": "   "}, CREATE_TEXTO_VACIO, "raw_text"),
        ({"incident_id": "INC-1", "raw_text": "a" * 10_001}, CREATE_TEXTO_DEMASIADO_LARGO, "raw_text"),
        ({"incident_id": "INC-1", "raw_text": TEXTO_P0, "title": "   "}, CREATE_TITULO_VACIO, "title"),
        ({"incident_id": "INC-1", "raw_text": TEXTO_P0, "title": "T" * 201}, CREATE_TITULO_DEMASIADO_LARGO, "title"),
        (
            {"incident_id": "INC-1", "raw_text": TEXTO_P0, "created_at": BASE.astimezone()},
            CREATE_CREACION_INVALIDA,
            "created_at",
        ),
    ],
)
def test_el_alta_rechaza_entradas_invalidas_sin_persistir(
    kwargs: dict, codigo: str, campo: str
) -> None:
    """FR-009/FR-024: cada regla tiene su código estable y no escribe nada."""
    repositorio = _RepositorioFalso()
    servicio = IncidentService(repositorio, clock=_RelojFijo())

    with pytest.raises(ValidationError) as excinfo:
        servicio.create_incident(**kwargs)

    assert excinfo.value.code == codigo
    assert excinfo.value.field == campo
    assert repositorio.guardados == []


def test_el_alta_informa_el_duplicado_y_persiste_la_clave() -> None:
    """US2: la detección se conecta dentro del alta y fija la clave de grupo."""
    original = _incidente(
        "INC-1", created_at=BASE - timedelta(minutes=5)
    )
    repositorio = _RepositorioFalso([original])
    servicio = IncidentService(repositorio, clock=_RelojFijo())

    resultado = servicio.create_incident("INC-2", TEXTO_P0)

    assert resultado.duplicate.is_duplicate is True
    assert resultado.duplicate.duplicate_of == ("INC-1",)
    assert resultado.incident.duplicate_group_key == "INC-1"
    assert repositorio.get_incident("INC-2") == resultado.incident


# ---------------------------------------------------------------------------
# US3 · Auditoría de SLA
# ---------------------------------------------------------------------------


def test_la_auditoria_devuelve_contexto_y_lee_el_reloj_una_sola_vez() -> None:
    """FR-017/FR-018: un instante, ventana y valores de la política."""
    repositorio = _RepositorioFalso([_incidente("INC-1")])
    reloj = _RelojFijo(BASE + timedelta(minutes=61))
    servicio = IncidentService(repositorio, clock=reloj)

    detalle = servicio.evaluate_incident_sla("INC-1")

    assert reloj.llamadas == 1
    assert detalle.incident.incident_id == "INC-1"
    assert detalle.reference_time == BASE + timedelta(minutes=61)
    assert detalle.evaluation.elapsed_minutes == 61
    assert detalle.evaluation.is_breached is True
    assert detalle.window == "24x7"


def test_la_auditoria_es_de_solo_lectura() -> None:
    """FR-025: auditar no escribe ni modifica ningún dato."""
    repositorio = _RepositorioFalso([_incidente("INC-1")])
    servicio = IncidentService(repositorio, clock=_RelojFijo())
    antes = list(repositorio.incidentes)

    servicio.evaluate_incident_sla("INC-1", BASE + timedelta(minutes=10))

    assert repositorio.guardados == []
    assert repositorio.incidentes == antes


def test_identificador_inexistente_es_no_encontrado() -> None:
    """FR-023: el caso de uso distingue la ausencia del incidente."""
    servicio = IncidentService(_RepositorioFalso(), clock=_RelojFijo())

    with pytest.raises(IncidentNotFoundError) as excinfo:
        servicio.evaluate_incident_sla("INC-404")

    assert excinfo.value.code == "SLA_INCIDENTE_NO_ENCONTRADO"


def test_identificador_vacio_es_entrada_invalida() -> None:
    """FR-017: el identificador vacío es `SLA_ID_VACIO`."""
    servicio = IncidentService(_RepositorioFalso(), clock=_RelojFijo())

    with pytest.raises(ValidationError) as excinfo:
        servicio.evaluate_incident_sla("   ")

    assert excinfo.value.code == SLA_ID_VACIO


def test_referencia_aware_es_entrada_invalida() -> None:
    """FR-024: una fecha con zona se rechaza antes de tocar el almacenamiento."""
    servicio = IncidentService(_RepositorioFalso(), clock=_RelojFijo())

    with pytest.raises(ValidationError) as excinfo:
        servicio.evaluate_incident_sla("INC-1", BASE.astimezone())

    assert excinfo.value.code == SLA_REFERENCIA_INVALIDA


def test_referencia_anterior_a_la_creacion_es_422() -> None:
    """FR-022: la referencia incoherente es 422 en HTTP y salida 1 en CLI."""
    servicio = IncidentService(
        _RepositorioFalso([_incidente("INC-1")]), clock=_RelojFijo()
    )

    with pytest.raises(DataInconsistencyError) as excinfo:
        servicio.evaluate_incident_sla("INC-1", BASE - timedelta(minutes=1))

    assert excinfo.value.code == SLA_REFERENCIA_INCONSISTENTE
    assert excinfo.value.status == 422


@pytest.mark.parametrize(
    "incidente",
    [
        _incidente("INC-1", status="RESOLVED", resolved_at=None),
        _incidente("INC-1", severity="P9"),
        _incidente(
            "INC-1",
            status="RESOLVED",
            resolved_at=BASE - timedelta(minutes=1),
        ),
    ],
)
def test_datos_incoherentes_son_409(incidente: Incident) -> None:
    """FR-031: sin valores por defecto ni documento parcial."""
    servicio = IncidentService(_RepositorioFalso([incidente]), clock=_RelojFijo())

    with pytest.raises(DataInconsistencyError) as excinfo:
        servicio.evaluate_incident_sla("INC-1", BASE)

    assert excinfo.value.code == SLA_DATOS_INCONSISTENTES
    assert excinfo.value.status == 409
