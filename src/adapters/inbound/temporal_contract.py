"""Validación ISO 8601 naive compartida por los contratos de entrada (D9).

Un único parser para el resumen, el alta y la auditoría de SLA: separador `T`
obligatorio, sin zona horaria y con la misma precisión fraccionaria admitida
por `datetime.fromisoformat` en Python 3.10.
"""

import re
from datetime import datetime
from typing import Any, Optional

from src.application.services import ValidationError

# `YYYY-MM-DDTHH:MM:SS[.ffffff]`: separador `T` obligatorio y sin zona horaria.
PATRON_INSTANTE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3}|\.\d{6})?$"
)


def parse_instante_naive(
    valor: Any, campo: str, codigo: str
) -> Optional[datetime]:
    """Valida un instante ISO 8601 naive o devuelve `None` si se omitió.

    Args:
        valor: Texto recibido del canal; `None` significa que se omitió. Un
            tipo distinto de texto se rechaza con el mismo código que un valor
            no parseable, porque el contrato lo trata como fecha inválida.
        campo: Nombre del campo para el documento de error.
        codigo: Código estable del contrato que se publica al rechazar.

    Raises:
        ValidationError: si el formato no es `YYYY-MM-DDTHH:MM:SS[.ffffff]`,
            no es parseable, no es texto o incluye zona horaria.
    """
    if valor is None:
        return None

    mensaje = (
        f"El campo {campo} debe usar el formato "
        "YYYY-MM-DDTHH:MM:SS[.ffffff], con separador 'T' y sin zona horaria."
    )
    if not isinstance(valor, str):
        raise ValidationError(codigo, campo, mensaje)

    texto = valor.strip()
    if not PATRON_INSTANTE.match(texto):
        raise ValidationError(codigo, campo, mensaje)

    try:
        instante = datetime.fromisoformat(texto)
    except ValueError as exc:
        raise ValidationError(codigo, campo, mensaje) from exc

    if instante.tzinfo is not None and instante.tzinfo.utcoffset(instante) is not None:
        raise ValidationError(codigo, campo, mensaje)
    return instante
