# Contrato CLI · Salud del servicio

**Comando**: `uv run python -m src.adapters.inbound.cli health`

**Opciones**: ninguna.

## Resultados

| Estado de la base | stdout | stderr | Salida |
|---|---|---|---|
| Responde | `{"status": "ok", "database": "connected"}` | vacío | `0` |
| No responde | `{"status": "error", "database": "unavailable"}` | vacío | `1` |
| Configuración inválida | vacío | `application/problem+json` con `code: "CONFIG_DATABASE_URL_INVALIDA"` | `2` |
| Fallo interno inesperado | vacío | `application/problem+json` con `code: "HEALTH_ERROR_INTERNO"` | `1` |

- El documento de salud es el **único** resultado del comando en stdout; se serializa con
  `json.dumps(..., ensure_ascii=False, indent=2)`.
- El documento es idéntico, campo a campo, al de `GET /health` para el mismo estado (SC-003).
- En indisponibilidad no se imprime `problem+json`, ni un mensaje adicional, ni una traza: el
  documento es el resultado.
- El comando no importa `src.adapters.inbound.api`; comparte `inbound/health_contract.py`.
- La configuración inválida ocurre antes de abrir conexión y antes de construir el repositorio.

## Forma del error de configuración

```json
{
  "type": "https://incidentops.local/errores/config-database-url-invalida",
  "title": "Configuración de base de datos inválida",
  "status": 422,
  "detail": "Esquema de DATABASE_URL no soportado: 'postgres'. Use 'sqlite:///ruta/incidentops.db', 'sqlite:///:memory:' o 'postgresql://usuario:clave@host:5432/base'.",
  "code": "CONFIG_DATABASE_URL_INVALIDA",
  "errors": [{"field": "DATABASE_URL", "code": "CONFIG_DATABASE_URL_INVALIDA"}]
}
```

El `detail` cita como máximo el esquema; nunca el DSN completo ni credenciales.

## Ejemplos

```bash
# Base disponible
uv run python -m src.adapters.inbound.cli health
# {"status": "ok", "database": "connected"} · salida 0

# Base caída
docker compose stop db
uv run python -m src.adapters.inbound.cli health
# {"status": "error", "database": "unavailable"} · salida 1

# Configuración inválida
$env:DATABASE_URL = "postgres://incidentops:clave@localhost:5432/incidentops"
uv run python -m src.adapters.inbound.cli health
# stderr: CONFIG_DATABASE_URL_INVALIDA · salida 2
```

## Reglas de paridad

- `status` y `database` coinciden con los de `GET /health` en el mismo estado y en el mismo instante.
- Sólo `/health` traduce una caída a 503; las operaciones de negocio conservan su error inesperado
  genérico (500 HTTP, salida 1 CLI) sin códigos nuevos.
