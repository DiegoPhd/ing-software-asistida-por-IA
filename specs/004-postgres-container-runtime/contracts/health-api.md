# Contrato HTTP · Salud del servicio

**Método y ruta**: `GET /health`

**Autenticación**: ninguna.

**Parámetros**: ninguno. Un parámetro de consulta adicional no forma parte del contrato; la ruta no
lo interpreta.

## Respuestas

| Estado de la base | HTTP | Cuerpo exacto |
|---|---|---|
| Responde a `SELECT 1` | `200 OK` | `{"status": "ok", "database": "connected"}` |
| No responde, credenciales inválidas o tiempo agotado | `503 Service Unavailable` | `{"status": "error", "database": "unavailable"}` |

Cabeceras en ambos casos:

- `Content-Type: application/json`
- `Cache-Control: no-store`

Documento conforme a [health.schema.json](./health.schema.json).

## Reglas

- Cada petición ejecuta una comprobación real de conectividad; no hay caché en el servidor ni se
  permite la de intermediarios (`no-store`).
- La comprobación no ejecuta DDL, no exige que existan las tablas y no calcula SLA.
- La espera de la comprobación está acotada a 2 s; la respuesta 503 llega en ≤ 3 s.
- Nunca se responde 500 por una caída de la base: el estado es 200 o 503.
- El cuerpo no expone motor, host, usuario, versión, latencia, mensaje del driver ni traza.
- Una caída posterior al último chequeo se informa en la siguiente consulta; una base que vuelve se
  informa como 200 sin reiniciar el proceso.
- Una configuración de motor inválida impide que la API arranque; no hay respuesta HTTP que
  documentar en ese caso (FR-018).

## Ejemplos

```bash
curl -i http://127.0.0.1:8000/health
```

```http
HTTP/1.1 200 OK
content-type: application/json
cache-control: no-store

{"status":"ok","database":"connected"}
```

```http
HTTP/1.1 503 Service Unavailable
content-type: application/json
cache-control: no-store

{"status":"error","database":"unavailable"}
```

El healthcheck del contenedor `api` consume esta misma ruta: un 503 marca el contenedor como no sano
y evita declararlo listo antes de tiempo.
