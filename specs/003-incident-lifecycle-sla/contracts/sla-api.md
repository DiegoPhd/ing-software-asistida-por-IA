# Contrato HTTP · Auditoría de SLA de un incidente

**Método y ruta**: `GET /api/v1/incidents/{incident_id}/sla`

**Parámetros de consulta**:

| Parámetro | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `reference_time` | texto ISO 8601 naive | No | Instante único de evaluación. `YYYY-MM-DDTHH:MM:SS[.ffffff]` con separador `T` y sin zona horaria. Si se omite, se aplica el instante actual y se informa |

Se rechaza cualquier otro parámetro, los parámetros repetidos y los valores con zona horaria.

**Respuesta 200**: documento de [sla-evaluation.schema.json](./sla-evaluation.schema.json).

```json
{
  "incident_id": "INC-3002",
  "severity": "P2",
  "status": "OPEN",
  "created_at": "2026-11-06T17:00:00",
  "resolved_at": null,
  "reference_time": "2026-11-09T09:00:00",
  "elapsed_minutes": 120,
  "allowed_minutes": 480,
  "remaining_minutes": 360,
  "is_breached": false,
  "requires_escalation": false,
  "window": "BUSINESS_HOURS"
}
```

- En un incidente terminal el cómputo se detiene en `resolved_at` y no crece con `reference_time`.
- `remaining_minutes` puede ser negativo cuando se incumple; no se recorta a cero.
- La auditoría es de sólo lectura.

## Errores

Todos usan `application/problem+json`.

| HTTP | `code` | Causa |
|---|---|---|
| 422 | `SLA_REFERENCIA_INVALIDA` | `reference_time` no parseable, con espacio, con zona horaria o tipo incorrecto |
| 422 | `SLA_SOLICITUD_INVALIDA` | Parámetro desconocido, repetido o petición no conforme |
| 422 | `SLA_REFERENCIA_INCONSISTENTE` | `reference_time` anterior a `created_at`; no se devuelven minutos negativos ni parciales |
| 409 | `SLA_DATOS_INCONSISTENTES` | Severidad o estado desconocidos en el almacenamiento, o `resolved_at` anterior a `created_at` |
| 404 | `SLA_INCIDENTE_NO_ENCONTRADO` | El identificador no corresponde a ningún incidente almacenado |
| 500 | `SLA_ERROR_INTERNO` | Fallo inesperado; no expone detalles internos |

Una ruta HTTP sin identificador no alcanza el endpoint (el router responde `404`); el código
`SLA_ID_VACIO` se reserva a la CLI, donde `--incident-id` puede llegar vacío o sólo con espacios.

## Ejemplos

```bash
curl "http://127.0.0.1:8000/api/v1/incidents/INC-3002/sla"
curl "http://127.0.0.1:8000/api/v1/incidents/INC-3002/sla?reference_time=2026-11-09T09:00:00"
```

## Reglas de paridad

- La CLI `sla` produce el mismo documento JSON para el mismo incidente y el mismo `reference_time`.
- Los fallos equivalentes comparten el mismo `code`; sólo difieren el estado HTTP y el código de
  salida (`422`/`404`/`409` → salida `1` cuando el dato es incoherente o inexistente, `2` cuando la
  entrada es inválida).
