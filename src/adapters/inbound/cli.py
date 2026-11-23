"""Subcomandos `triage`, `summary`, `create`, `sla` y `health` del adaptador CLI.

Traduce terminal a caso de uso y formatea el resultado como JSON; no clasifica,
no calcula SLA, no decide equivalencias ni importa el adaptador HTTP.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Tuple

import typer

from src.adapters.inbound.health_contract import to_health_response
from src.adapters.inbound.lifecycle_contract import (
    to_incident_created_response,
    to_sla_evaluation_response,
)
from src.adapters.inbound.problem import build_problem
from src.adapters.inbound.summary_contract import (
    parse_reference_time,
    to_summary_response,
)
from src.adapters.inbound.temporal_contract import parse_instante_naive
from src.adapters.outbound.factory import ConfigurationError, build_incident_service
from src.application.services import (
    CREATE_CREACION_INVALIDA,
    CREATE_ERROR_INTERNO,
    SLA_ERROR_INTERNO,
    SLA_REFERENCIA_INVALIDA,
    SUMMARY_ERROR_INTERNO,
    DataInconsistencyError,
    IncidentAlreadyExistsError,
    IncidentNotFoundError,
    ValidationError,
)

TRIAGE_FUENTE_TEXTO_INVALIDA = "TRIAGE_FUENTE_TEXTO_INVALIDA"
TRIAGE_ARCHIVO_INVALIDO = "TRIAGE_ARCHIVO_INVALIDO"
TRIAGE_ID_CONFLICTO = "TRIAGE_ID_CONFLICTO"

CONFIG_DATABASE_URL_INVALIDA = "CONFIG_DATABASE_URL_INVALIDA"
HEALTH_ERROR_INTERNO = "HEALTH_ERROR_INTERNO"

app = typer.Typer(
    add_completion=False,
    help="CLI de IncidentOps para probar reportes desde la terminal.",
)


@app.callback()
def main() -> None:
    """IncidentOps · utilidades de operación.

    El callback mantiene la aplicación como grupo de subcomandos, de modo que
    `triage` se invoque siempre por su nombre.
    """


class _EntradaInvalida(Exception):
    """Fallo de entrada propio del adaptador CLI."""

    def __init__(self, code: str, field: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.field = field
        self.detail = detail


def _emitir_error(code: str, field: str, detail: str, status: int = 422) -> None:
    typer.echo(
        json.dumps(
            build_problem(code, field, detail, status=status), ensure_ascii=False, indent=2
        ),
        err=True,
    )


def _leer_archivo(ruta: Path, incident_id: Optional[str]) -> Tuple[str, str]:
    try:
        contenido = ruta.read_text(encoding="utf-8")
    except OSError as exc:
        raise _EntradaInvalida(
            TRIAGE_ARCHIVO_INVALIDO,
            "file",
            f"No se pudo leer el archivo {ruta}: {exc}",
        ) from exc

    try:
        datos = json.loads(contenido)
    except json.JSONDecodeError as exc:
        raise _EntradaInvalida(
            TRIAGE_ARCHIVO_INVALIDO,
            "file",
            f"El archivo {ruta} no contiene JSON válido: {exc}",
        ) from exc

    if not isinstance(datos, dict):
        raise _EntradaInvalida(
            TRIAGE_ARCHIVO_INVALIDO,
            "file",
            "El archivo debe contener un único objeto de reporte, no una lista.",
        )

    texto = datos.get("raw_text")
    if not isinstance(texto, str):
        raise _EntradaInvalida(
            TRIAGE_ARCHIVO_INVALIDO,
            "raw_text",
            "El archivo debe incluir raw_text como texto.",
        )

    id_archivo = datos.get("incident_id")
    if id_archivo is not None and not isinstance(id_archivo, str):
        raise _EntradaInvalida(
            TRIAGE_ARCHIVO_INVALIDO,
            "incident_id",
            "El campo incident_id del archivo debe ser texto.",
        )

    if (
        incident_id is not None
        and id_archivo is not None
        and incident_id.strip() != id_archivo.strip()
    ):
        raise _EntradaInvalida(
            TRIAGE_ID_CONFLICTO,
            "incident_id",
            "El --incident-id y el incident_id del archivo no coinciden.",
        )

    id_final = incident_id if incident_id is not None else (id_archivo or "")
    return id_final, texto


def _resolver_entrada(
    incident_id: Optional[str], raw_text: Optional[str], archivo: Optional[Path]
) -> Tuple[str, str]:
    if raw_text is not None and archivo is not None:
        raise _EntradaInvalida(
            TRIAGE_FUENTE_TEXTO_INVALIDA,
            "raw_text",
            "Use --raw-text o --file, no ambos.",
        )
    if raw_text is None and archivo is None:
        raise _EntradaInvalida(
            TRIAGE_FUENTE_TEXTO_INVALIDA,
            "raw_text",
            "Debe indicar --raw-text, --raw-text - o --file.",
        )

    if archivo is not None:
        return _leer_archivo(archivo, incident_id)

    texto = sys.stdin.read() if raw_text == "-" else (raw_text or "")
    return incident_id or "", texto


@app.command("triage")
def triage(
    incident_id: Optional[str] = typer.Option(
        None,
        "--incident-id",
        help="Identificador del incidente; puede venir en --file.",
    ),
    raw_text: Optional[str] = typer.Option(
        None,
        "--raw-text",
        help="Texto del reporte. Use '-' para leerlo de la entrada estándar.",
    ),
    archivo: Optional[Path] = typer.Option(
        None,
        "--file",
        help="Archivo JSON con un único reporte {incident_id, raw_text}.",
    ),
) -> None:
    """Clasifica un reporte y escribe el resultado en JSON sobre stdout."""
    try:
        id_final, texto = _resolver_entrada(incident_id, raw_text, archivo)
        resultado = build_incident_service().triage_incident(id_final, texto)
    except _EntradaInvalida as exc:
        _emitir_error(exc.code, exc.field, exc.detail)
        raise typer.Exit(2)
    except ValidationError as exc:
        _emitir_error(exc.code, exc.field, exc.detail)
        raise typer.Exit(2)
    except Exception as exc:  # noqa: BLE001 - el borde traduce cualquier fallo a código 1
        typer.echo(f"Error inesperado: {exc}", err=True)
        raise typer.Exit(1)

    typer.echo(json.dumps(asdict(resultado), ensure_ascii=False, indent=2))


@app.command("summary")
def summary(
    component: Optional[str] = typer.Option(
        None,
        "--component",
        help="Filtra por componente exacto; ausente o vacío significa todos.",
    ),
    reference_time: Optional[str] = typer.Option(
        None,
        "--reference-time",
        help="Instante ISO 8601 naive: YYYY-MM-DDTHH:MM:SS[.ffffff].",
    ),
) -> None:
    """Escribe en stdout el resumen de incidentes activos en JSON."""
    try:
        instante = parse_reference_time(reference_time)
        resumen = build_incident_service().get_active_incidents_summary(
            reference_time=instante,
            component_filter=component,
        )
    except ValidationError as exc:
        _emitir_error(exc.code, exc.field, exc.detail)
        raise typer.Exit(2)
    except DataInconsistencyError as exc:
        _emitir_error(exc.code, exc.field, exc.detail, status=exc.status)
        raise typer.Exit(1)
    except Exception:
        _emitir_error(
            SUMMARY_ERROR_INTERNO,
            "summary",
            "No fue posible construir el resumen.",
            status=500,
        )
        raise typer.Exit(1)

    documento = to_summary_response(resumen).model_dump()
    typer.echo(json.dumps(documento, ensure_ascii=False, indent=2))


@app.command("create")
def create(
    incident_id: Optional[str] = typer.Option(
        None,
        "--incident-id",
        help="Identificador único del incidente; no vacío y máximo 64 caracteres.",
    ),
    raw_text: Optional[str] = typer.Option(
        None,
        "--raw-text",
        help="Texto original del reporte; no vacío y máximo 10 000 caracteres.",
    ),
    title: Optional[str] = typer.Option(
        None,
        "--title",
        help="Título opcional; si se omite se deriva de la primera línea del texto.",
    ),
    created_at: Optional[str] = typer.Option(
        None,
        "--created-at",
        help="Instante ISO 8601 naive: YYYY-MM-DDTHH:MM:SS[.ffffff].",
    ),
) -> None:
    """Registra un incidente y escribe el documento JSON de alta en stdout."""
    try:
        instante = parse_instante_naive(
            created_at, "created_at", CREATE_CREACION_INVALIDA
        )
        resultado = build_incident_service().create_incident(
            incident_id or "",
            raw_text or "",
            title=title,
            created_at=instante,
        )
    except ValidationError as exc:
        _emitir_error(exc.code, exc.field, exc.detail)
        raise typer.Exit(2)
    except IncidentAlreadyExistsError as exc:
        _emitir_error(exc.code, exc.field, exc.detail, status=409)
        raise typer.Exit(1)
    except DataInconsistencyError as exc:
        _emitir_error(exc.code, exc.field, exc.detail, status=exc.status)
        raise typer.Exit(1)
    except Exception:
        _emitir_error(
            CREATE_ERROR_INTERNO,
            "create",
            "No fue posible registrar el incidente.",
            status=500,
        )
        raise typer.Exit(1)

    documento = to_incident_created_response(resultado).model_dump(mode="json")
    typer.echo(json.dumps(documento, ensure_ascii=False, indent=2))


@app.command("health")
def health() -> None:
    """Comprueba la conectividad real y escribe el documento de salud en stdout.

    Sale 0 si la base responde y 1 si no; la configuración inválida sale 2 con
    `problem+json` en stderr, sin documento ni traza (FR-003/FR-018).
    """
    try:
        servicio = build_incident_service()
    except ConfigurationError as exc:
        _emitir_error(
            CONFIG_DATABASE_URL_INVALIDA,
            "DATABASE_URL",
            str(exc),
            status=422,
        )
        raise typer.Exit(2)
    except Exception:
        _emitir_error(
            HEALTH_ERROR_INTERNO,
            "health",
            "No fue posible construir el servicio de salud.",
            status=500,
        )
        raise typer.Exit(1)

    try:
        documento = to_health_response(servicio.check_health())
    except Exception:
        _emitir_error(
            HEALTH_ERROR_INTERNO,
            "health",
            "No fue posible comprobar la conectividad del servicio.",
            status=500,
        )
        raise typer.Exit(1)

    typer.echo(json.dumps(documento.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if documento.status != "ok":
        raise typer.Exit(1)


@app.command("sla")
def sla(
    incident_id: Optional[str] = typer.Option(
        None,
        "--incident-id",
        help="Identificador del incidente almacenado; no vacío.",
    ),
    reference_time: Optional[str] = typer.Option(
        None,
        "--reference-time",
        help="Instante ISO 8601 naive: YYYY-MM-DDTHH:MM:SS[.ffffff].",
    ),
) -> None:
    """Audita el SLA de un incidente y escribe el documento JSON en stdout."""
    try:
        instante = parse_instante_naive(
            reference_time, "reference_time", SLA_REFERENCIA_INVALIDA
        )
        detalle = build_incident_service().evaluate_incident_sla(
            incident_id or "", instante
        )
    except ValidationError as exc:
        _emitir_error(exc.code, exc.field, exc.detail)
        raise typer.Exit(2)
    except IncidentNotFoundError as exc:
        _emitir_error(exc.code, exc.field, exc.detail, status=404)
        raise typer.Exit(1)
    except DataInconsistencyError as exc:
        _emitir_error(exc.code, exc.field, exc.detail, status=exc.status)
        raise typer.Exit(1)
    except Exception:
        _emitir_error(
            SLA_ERROR_INTERNO,
            "sla",
            "No fue posible auditar el SLA del incidente.",
            status=500,
        )
        raise typer.Exit(1)

    documento = to_sla_evaluation_response(detalle).model_dump(mode="json")
    typer.echo(json.dumps(documento, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
