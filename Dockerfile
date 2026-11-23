# syntax=docker/dockerfile:1
# Imagen de la API de IncidentOps (ADR-008): multietapa, sin cadena de
# compilación en runtime, dependencias fijadas por uv.lock y usuario sin
# privilegios. No contiene credenciales, DSN ni estado persistente.

FROM python:3.12-slim AS builder

# Imagen de uv fijada por etiqueta: el build no resuelve versiones distintas.
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY src ./src

RUN groupadd --system --gid 10001 incidentops \
    && useradd --system --uid 10001 --gid incidentops --no-create-home incidentops

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "src.adapters.inbound.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
