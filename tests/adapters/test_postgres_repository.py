"""Pruebas unitarias del adaptador PostgreSQL sin un motor real.

Cubren la comprobación de salud acotada (RNF-002): la resolución DNS de un
contenedor detenido puede tardar más que `connect_timeout`, por lo que el
adaptador impone un plazo propio y nunca propaga la excepción al puerto.
"""

import threading
import time
from typing import Any, Optional

import psycopg
import pytest

import src.adapters.outbound.postgres_repository as modulo
from src.adapters.outbound.postgres_repository import PostgresIncidentRepository


class _CursorFalso:
    """Cursor mínimo con una fila fija."""

    def __init__(self, fila: Optional[dict]) -> None:
        self._fila = fila

    def __enter__(self) -> "_CursorFalso":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def execute(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def fetchone(self) -> Optional[dict]:
        return self._fila


class _ConexionFalsa:
    """Conexión mínima que delega en el cursor falso."""

    def __init__(self, fila: Optional[dict]) -> None:
        self._fila = fila

    def __enter__(self) -> "_ConexionFalsa":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False

    def cursor(self) -> _CursorFalso:
        return _CursorFalso(self._fila)


class _RepositorioDePrueba(PostgresIncidentRepository):
    """Evita red y esquema: el comportamiento de `_connect` se inyecta."""

    def __init__(self, conectar: Any) -> None:
        self._dsn = "postgresql://no-usado/base"
        self._schema_ready = True
        self._schema_lock = threading.Lock()
        self._conectar = conectar

    def _connect(self) -> Any:
        return self._conectar()


def test_la_salud_es_verdadera_solo_si_hay_fila() -> None:
    repositorio = _RepositorioDePrueba(lambda: _ConexionFalsa({"ok": 1}))

    assert repositorio.check_health() is True


def test_la_salud_informa_falso_ante_error_de_conexion() -> None:
    def _falla() -> Any:
        raise psycopg.OperationalError("no disponible")

    assert _RepositorioDePrueba(_falla).check_health() is False


def test_la_salud_no_espera_mas_que_el_plazo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RNF-002: la comprobación se corta y responde `False` sin excepción."""

    def _lenta() -> Any:
        time.sleep(0.5)
        return _ConexionFalsa({"ok": 1})

    monkeypatch.setattr(modulo, "TIEMPO_DE_COMPROBACION_SEGUNDOS", 0.05)
    inicio = time.perf_counter()

    resultado = _RepositorioDePrueba(_lenta).check_health()

    transcurrido = time.perf_counter() - inicio
    assert resultado is False
    assert transcurrido < 0.4
