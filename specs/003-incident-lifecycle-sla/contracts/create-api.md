# Contrato HTTP · Alta persistente de incidentes

**Método y ruta**: `POST /api/v1/incidents`

**Cuerpo** (`application/json`, campos desconocidos rechazados):

| Campo | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `incident_id` | texto | Sí | Único; recortado; no vacío; máximo 64 caracteres |
| `raw_text` | texto | Sí | Texto original sin normalizar; recortado para validar; máximo 10 000 caracteres |
| `title` | texto | No | Si se omite, se deriva del texto (primera línea, máximo 200). Si se indica, no vacío y máximo 200 |
| `created_at` | texto ISO 8601 naive | No | `YYYY-MM-DDTHH:MM:SS[.ffffff]` con separador `T` y sin zona horaria. Si se omite, se usa el instante de la solicitud y se informa |

```json
{
  "incident_id": "INC-3001",
  "raw_text": "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta.",
  "created_at": "2026-11-20T10:00:00"
}
```

**Respuesta 201**: documento de [incident-created.schema.json](./incident-created.schema.json).

Se rechaza con `422 CREATE_SOLICITUD_INVALIDA` cualquier parámetro de consulta desconocido o repetido,
igual que un campo desconocido en el cuerpo.

```json
{
  "incident_id": "INC-3002",
  "title": "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta.",
  "component": "payments-gateway",
  "severity": "P0",
  "recommended_team": "Backend-Core",
  "status": "OPEN",
  "created_at": "2026-11-20T10:05:00",
  "resolved_at": null,
  "duplicate_group_key": "INC-3001",
  "is_duplicate": true,
  "duplicate_of": ["INC-3001"]
}
```

Se responde `201` tanto si hay duplicados como si no. El aviso es informativo: no fusiona ni modifica
incidentes existentes.

## Errores

Todos usan `application/problem+json` con `type`, `title`, `status`, `detail`, `code` y `errors[]`.

| HTTP | `code` | Causa |
|---|---|---|
| 422 | `CREATE_ID_VACIO` | Identificador vacío o sólo espacios |
| 422 | `CREATE_ID_DEMASIADO_LARGO` | Identificador de más de 64 caracteres |
| 422 | `CREATE_TEXTO_VACIO` | Texto vacío o sólo espacios |
| 422 | `CREATE_TEXTO_DEMASIADO_LARGO` | Texto de más de 10 000 caracteres |
| 422 | `CREATE_TITULO_VACIO` | Título indicado vacío o sólo espacios |
| 422 | `CREATE_TITULO_DEMASIADO_LARGO` | Título de más de 200 caracteres |
| 422 | `CREATE_CREACION_INVALIDA` | `created_at` no parseable, con espacio, con zona horaria o tipo incorrecto |
| 422 | `CREATE_SOLICITUD_INVALIDA` | Campo desconocido, cuerpo no conforme o JSON inválido |
| 409 | `CREATE_ID_CONFLICTO` | El identificador ya corresponde a un incidente almacenado |
| 500 | `CREATE_ERROR_INTERNO` | Fallo inesperado; no expone detalles internos |

Un `409` no sobrescribe ni altera el incidente previo y no persiste nada del nuevo.

## Ejemplos

```bash
curl -X POST http://127.0.0.1:8000/api/v1/incidents \
  -H "Content-Type: application/json" \
  -d '{"incident_id":"INC-3001","raw_text":"Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta.","created_at":"2026-11-20T10:00:00"}'
```

## Reglas de paridad

- La CLI `create` produce el mismo documento JSON para la misma entrada y el mismo `created_at`.
- `is_duplicate` es verdadero si y sólo si `duplicate_of` no está vacío, y
  `duplicate_group_key` es nula si y sólo si `duplicate_of` está vacío.
- `duplicate_of` se ordena de más antiguo a más reciente, con desempate por identificador ascendente,
  y sólo contiene equivalentes previos.
