"""Benchmark de extremo a extremo del resumen de activos (HTTP y CLI).

No forma parte de `pytest` ni hace aserciones de tiempo: siembra una base
temporal y reporta la evidencia de SC-001 para `docs/adr/005`.

Uso:
    uv run python tools/benchmark_summary.py --records 10000 --iterations 20
"""

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from fastapi.testclient import TestClient  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from src.adapters.inbound.api.app import create_app  # noqa: E402
from src.adapters.inbound.cli import app as cli_app  # noqa: E402
from src.adapters.outbound.sqlite_repository import (  # noqa: E402
    SQLiteIncidentRepository,
)

RUTA = "/api/v1/incidents/summary"
REFERENCIA = "2026-11-20T12:00:00"
COMPONENTE = "payments-gateway"


def _sembrar(ruta: Path, registros: int) -> None:
    SQLiteIncidentRepository(str(ruta)).seed_synthetic_incidents(registros)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark HTTP/CLI del resumen de incidentes activos"
    )
    parser.add_argument(
        "--records", type=int, default=10000, help="Incidentes activos a sembrar"
    )
    parser.add_argument(
        "--iterations", type=int, default=20, help="Consultas por canal a medir"
    )
    args = parser.parse_args()

    if args.iterations < 1:
        parser.error("--iterations debe ser al menos 1")

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as carpeta:
        ruta = Path(carpeta) / "benchmark.db"
        print(f"Sembrando {args.records} incidentes activos en {ruta}...")
        _sembrar(ruta, args.records)
        os.environ["DATABASE_URL"] = f"sqlite:///{ruta}"

        cliente = TestClient(create_app())
        parametros_http = {
            "reference_time": REFERENCIA,
            "component": COMPONENTE,
        }
        calentamiento = cliente.get(RUTA, params=parametros_http)
        assert calentamiento.status_code == 200, calentamiento.text

        inicio = time.perf_counter()
        for _ in range(args.iterations):
            respuesta = cliente.get(RUTA, params=parametros_http)
            assert respuesta.status_code == 200, respuesta.text
        http_ms = (time.perf_counter() - inicio) * 1000

        runner = CliRunner()
        argumentos = [
            "summary",
            "--component",
            COMPONENTE,
            "--reference-time",
            REFERENCIA,
        ]
        calentamiento_cli = runner.invoke(cli_app, argumentos)
        assert calentamiento_cli.exit_code == 0, calentamiento_cli.stderr

        inicio = time.perf_counter()
        for _ in range(args.iterations):
            salida = runner.invoke(cli_app, argumentos)
            assert salida.exit_code == 0, salida.stderr
        cli_ms = (time.perf_counter() - inicio) * 1000

        documento = json.loads(salida.stdout)
        print("=== Benchmark de extremo a extremo (SC-001) ===")
        print(f"Incidentes activos sembrados: {args.records}")
        print(f"Componente filtrado: {COMPONENTE}")
        print(f"Activos devueltos: {documento['total_active']}")
        print(f"Incumplidos: {documento['breached_count']}")
        print(f"HTTP · {args.iterations} consultas: {http_ms:.2f} ms")
        print(f"HTTP · promedio: {http_ms / args.iterations:.2f} ms")
        print(f"CLI  · {args.iterations} consultas: {cli_ms:.2f} ms")
        print(f"CLI  · promedio: {cli_ms / args.iterations:.2f} ms")
        print(
            "Objetivo SC-001 (< 1 s por consulta): "
            f"HTTP {'OK' if http_ms / args.iterations < 1000 else 'FUERA'}, "
            f"CLI {'OK' if cli_ms / args.iterations < 1000 else 'FUERA'}"
        )


if __name__ == "__main__":
    main()
