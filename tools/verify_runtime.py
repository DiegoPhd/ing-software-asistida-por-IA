"""Verificación del despliegue de referencia con Docker Compose (O-01/O-02).

`--compose` levanta la topología, espera a que `db` y `api` estén sanos y
comprueba el 200 de `/health`. `--resiliencia` añade la caída controlada de la
base (503 acotado), la recuperación sin reiniciar la API y la persistencia tras
recrear la API. Se mide el p95 de `/health` con la base sana y el tiempo de la
respuesta 503. El script no usa PyYAML: habla con `docker compose` y con HTTP.

Uso:
    uv run python tools/verify_runtime.py --compose
    uv run python tools/verify_runtime.py --compose --resiliencia
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from math import ceil
from typing import Any, Dict, List, Optional, Tuple

PUERTO = int(os.getenv("API_PORT", "8000"))
BASE_URL = f"http://127.0.0.1:{PUERTO}"
URL_SALUD = f"{BASE_URL}/health"
TIEMPO_ESPERA_SERVICIOS = 180
TIEMPO_ESPERA_RECUPERACION = 15
P95_MAXIMO_MS = 200.0
TIEMPO_503_MAXIMO_SEGUNDOS = 3.0
MUESTRAS_LATENCIA = 25


class VerificacionFallida(RuntimeError):
    """La comprobación no cumple el contrato del runtime."""


def _ejecutar(*argumentos: str, timeout: int = TIEMPO_ESPERA_SERVICIOS) -> str:
    """Ejecuta `docker compose` y devuelve su salida estándar."""
    comando = ["docker", "compose", *argumentos]
    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise VerificacionFallida(
            "Docker no está disponible en este host; instale Docker y Compose v2."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise VerificacionFallida(
            f"El comando '{' '.join(comando)}' superó {timeout} s."
        ) from exc

    if resultado.returncode != 0:
        detalle = (resultado.stderr or resultado.stdout or "").strip()
        raise VerificacionFallida(
            f"El comando '{' '.join(comando)}' falló: {detalle}"
        )
    return resultado.stdout


def _peticion(
    url: str, metodo: str = "GET", cuerpo: Optional[Dict[str, Any]] = None
) -> Tuple[int, Dict[str, Any]]:
    """Realiza una petición HTTP y devuelve estado y documento JSON."""
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    cabeceras = {"Content-Type": "application/json"} if datos is not None else {}
    peticion = urllib.request.Request(
        url, data=datos, method=metodo, headers=cabeceras
    )
    try:
        with urllib.request.urlopen(peticion, timeout=5) as respuesta:
            return respuesta.status, json.loads(respuesta.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def _esperar_salud(esperado: int, limite: float) -> float:
    """Espera a que `/health` devuelva el estado esperado y mide el tiempo."""
    inicio = time.perf_counter()
    ultimo: Optional[int] = None
    while time.perf_counter() - inicio <= limite:
        try:
            estado, _ = _peticion(URL_SALUD)
            ultimo = estado
            if estado == esperado:
                return time.perf_counter() - inicio
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            ultimo = None
        time.sleep(0.5)
    raise VerificacionFallida(
        f"/health no llegó a {esperado} en {limite:.0f} s (último estado: {ultimo})."
    )


def _esperar_sanos() -> None:
    """Espera a que los servicios declarados estén sanos."""
    _ejecutar("up", "-d", "--build", "--wait", "--wait-timeout", "120")
    for servicio in ("db", "api"):
        salida = _ejecutar("ps", "--format", "{{.Service}} {{.Health}}")
        estado = {
            linea.split()[0]: (linea.split() + [""])[1]
            for linea in salida.splitlines()
            if linea.strip()
        }
        if estado.get(servicio) != "healthy":
            raise VerificacionFallida(
                f"El servicio '{servicio}' no está sano: {estado.get(servicio, 'ausente')}."
            )


def _comprobar_conectado() -> None:
    estado, documento = _peticion(URL_SALUD)
    if estado != 200 or documento != {"status": "ok", "database": "connected"}:
        raise VerificacionFallida(
            f"/health no informa connected: {estado} {documento}"
        )


def _p95(muestras: List[float]) -> float:
    ordenadas = sorted(muestras)
    return ordenadas[max(ceil(0.95 * len(ordenadas)) - 1, 0)]


def _medir_latencia() -> float:
    """Mide el p95 de `/health` con la base sana (≥ 20 peticiones)."""
    muestras: List[float] = []
    for _ in range(MUESTRAS_LATENCIA):
        inicio = time.perf_counter()
        estado, _ = _peticion(URL_SALUD)
        muestras.append((time.perf_counter() - inicio) * 1000)
        if estado != 200:
            raise VerificacionFallida(f"/health devolvió {estado} durante la medición.")
    valor = _p95(muestras)
    if valor > P95_MAXIMO_MS:
        raise VerificacionFallida(
            f"p95 de /health {valor:.1f} ms > {P95_MAXIMO_MS:.0f} ms."
        )
    return valor


def _comprobar_resiliencia() -> Tuple[float, float]:
    """Caída → 503 → recuperación a 200 y latencia acotada de la caída."""
    print("· Deteniendo la base y comprobando el 503...")
    _ejecutar("stop", "db")
    inicio = time.perf_counter()
    estado, documento = _peticion(URL_SALUD)
    tiempo_503 = time.perf_counter() - inicio
    if estado != 503 or documento != {
        "status": "error",
        "database": "unavailable",
    }:
        raise VerificacionFallida(
            f"Con la base detenida se esperaba 503 unavailable: {estado} {documento}"
        )
    if tiempo_503 > TIEMPO_503_MAXIMO_SEGUNDOS:
        raise VerificacionFallida(
            f"El 503 tardó {tiempo_503:.2f} s > {TIEMPO_503_MAXIMO_SEGUNDOS:.0f} s."
        )

    print("· Reiniciando la base y esperando la recuperación sin reiniciar la API...")
    _ejecutar("start", "db")
    tiempo_recuperacion = _esperar_salud(200, TIEMPO_ESPERA_RECUPERACION)
    return tiempo_503, tiempo_recuperacion


def _comprobar_persistencia() -> None:
    """Crea un incidente, recrea la API y comprueba que sigue consultable."""
    incidente = f"INC-VERIFY-{int(time.time())}"
    texto = "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta."
    estado, _ = _peticion(
        f"{BASE_URL}/api/v1/incidents",
        metodo="POST",
        cuerpo={
            "incident_id": incidente,
            "raw_text": texto,
            "created_at": "2026-11-20T10:00:00",
        },
    )
    if estado != 201:
        raise VerificacionFallida(f"El alta de verificación devolvió {estado}.")

    print("· Recreando la API y verificando que el dato persiste...")
    _ejecutar("up", "-d", "--force-recreate", "--no-deps", "api")
    _esperar_salud(200, TIEMPO_ESPERA_SERVICIOS)
    estado, documento = _peticion(
        f"{BASE_URL}/api/v1/incidents/{incidente}/sla",
        metodo="GET",
    )
    if estado != 200 or documento.get("incident_id") != incidente:
        raise VerificacionFallida(
            f"El incidente {incidente} no sobrevivió a recrear la API: {estado} {documento}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verificación del despliegue de referencia de IncidentOps"
    )
    parser.add_argument(
        "--compose",
        action="store_true",
        help="Levanta Compose y comprueba el arranque ordenado y la salud.",
    )
    parser.add_argument(
        "--resiliencia",
        action="store_true",
        help="Añade caída, 503, recuperación y persistencia.",
    )
    args = parser.parse_args()

    if not args.compose:
        parser.error("Indique --compose para verificar el despliegue de referencia.")

    try:
        print("· Levantando el despliegue de referencia y esperando servicios sanos...")
        _esperar_sanos()
        _comprobar_conectado()

        latencia = _medir_latencia()
        print(f"  /health sano · p95 {latencia:.1f} ms (≤ {P95_MAXIMO_MS:.0f} ms)")

        if args.resiliencia:
            tiempo_503, recuperacion = _comprobar_resiliencia()
            print(
                f"  503 en {tiempo_503:.2f} s (≤ {TIEMPO_503_MAXIMO_SEGUNDOS:.0f} s) · "
                f"recuperación en {recuperacion:.1f} s"
            )
            _comprobar_persistencia()
            print("  Persistencia verificada tras recrear la API.")

        print("Verificación completada: el despliegue de referencia cumple el contrato.")
        return 0
    except VerificacionFallida as exc:
        print(f"Verificación fallida: {exc}", file=sys.stderr)
        return 1
    finally:
        # `down` sin `-v` conserva el volumen nombrado (RNF-004).
        try:
            _ejecutar("down", timeout=120)
        except VerificacionFallida as exc:
            print(f"Aviso: no se pudo detener el despliegue: {exc}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
