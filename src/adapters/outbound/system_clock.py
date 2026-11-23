"""Reloj del sistema como implementación del puerto `ClockPort` (D12).

Vive en el adaptador de salida porque es una fuente externa de tiempo; el
dominio sigue recibiendo el instante como argumento explícito.
"""

from datetime import datetime


class SystemClock:
    """Reloj naive local usado por la raíz de composición en producción."""

    def now(self) -> datetime:
        """Devuelve el instante actual sin zona horaria."""
        return datetime.now()
