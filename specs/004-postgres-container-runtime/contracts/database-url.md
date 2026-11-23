# Contrato de configuración · `DATABASE_URL`

`src/adapters/outbound/factory.py` es el único punto que interpreta el DSN (FR-007). Ningún adaptador
de entrada lee la variable ni instancia una clase concreta.

## Matriz de selección

| `DATABASE_URL` | Repositorio | Notas |
|---|---|---|
| Ausente (variable no definida) | `SQLiteIncidentRepository(":memory:")` | Ruta local por defecto, sin infraestructura |
| `sqlite:///:memory:` | `SQLiteIncidentRepository(":memory:")` | Efímero por definición |
| `sqlite:///ruta/incidentops.db` | `SQLiteIncidentRepository(ruta)` | Archivo local |
| `postgresql://usuario:clave@host:5432/base` | `PostgresIncidentRepository(dsn)` | Motor dedicado |
| Vacía (`""`) o solo espacios | `ConfigurationError` | Debe fallar antes de abrir conexión; nunca cae a memoria |
| `postgres://…` | `ConfigurationError` | Alias no admitido por ADR-004 |
| `sqlite://` o `sqlite:///` sin ruta | `ConfigurationError` | Falta archivo o memoria |
| Cualquier otro esquema | `ConfigurationError` | Sin fallback silencioso |

## Comportamiento por canal

| Canal | Configuración inválida |
|---|---|
| API | `create_app()` falla al componer el servicio; Uvicorn no arranca |
| CLI `health` | `application/problem+json` en stderr con `CONFIG_DATABASE_URL_INVALIDA`, salida 2, sin documento ni traza |
| CLI de negocio | Error inesperado genérico con salida 1, sin detalle interno |

## Seguridad

- El mensaje de `ConfigurationError` incluye solo el esquema detectado (por ejemplo, `postgres`), no
  el usuario, la contraseña, el host ni la base.
- El DSN nunca se escribe en logs, documentos de salud, mensajes de error ni en la imagen.
- En Compose, las credenciales entran por entorno; `.env.example` contiene marcadores y `.env` está
  ignorado por Git.
- Una contraseña con caracteres especiales debe codificarse para URL antes de componer el DSN.

## Ejemplos

```bash
# Desarrollo sin infraestructura
unset DATABASE_URL

# Archivo local
export DATABASE_URL="sqlite:///incidentops.db"

# PostgreSQL del despliegue de referencia
export DATABASE_URL="postgresql://incidentops:incidentops_local@localhost:5432/incidentops"
```

En el host, el puerto `5432` no está publicado por el despliegue de referencia; el ejemplo con
`localhost` aplica solo si el operador decide publicar la base de forma explícita.
