"""Subcomando `triage` del adaptador CLI.

Traduce terminal a caso de uso y formatea el resultado como JSON; no clasifica
ni calcula nada por su cuenta.
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional, Tuple

import typer

from src.adapters.inbound.problem import build_problem
from src.application.services import ValidationError
from src.composition import build_incident_service

TRIAGE_FUENTE_TEXTO_INVALIDA = "TRIAGE_FUENTE_TEXTO_INVALIDA"
TRIAGE_ARCHIVO_INVALIDO = "TRIAGE_ARCHIVO_INVALIDO"
TRIAGE_ID_CONFLICTO = "TRIAGE_ID_CONFLICTO"

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


def _emitir_error(code: str, field: str, detail: str) -> None:
    typer.echo(
        json.dumps(build_problem(code, field, detail, status=422), ensure_ascii=False, indent=2),
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
