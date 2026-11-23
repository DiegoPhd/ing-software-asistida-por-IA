# Contrato HTTP · Resumen de Incidentes Activos

**Método y ruta**: `GET /api/v1/incidents/summary`

**Parámetros de consulta**:

| Parámetro | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `component` | texto | No | Comparación exacta contra el componente almacenado, ignorando espacios al inicio y al final. Ausente o vacío significa todos. Máximo 128 caracteres |
| `reference_time` | texto ISO 8601 naive | No | Instante único de evaluación. Formato `YYYY-MM-DDTHH:MM:SS[.ffffff]`, sin zona horaria y con separador `T` obligatorio (un espacio se rechaza); se valida con el mismo analizador que la CLI. Si se omite, se usa el instante actual |

**Respuesta 200**: documento de [summary.schema.json](./summary.schema.json). Un componente sin coincidencias y la ausencia total de activos también responden `200` con `total_active: 0`, `breached_count: 0` e `incidents: []`.

```json
{
  "total_active": 2,
  "breached_count": 1,
  "incidents": [
    {
      "incident_id": "INC-2001",
      "title": "Pasarela de pagos caída",
      "component": "payments-gateway",
      "severity": "P0",
      "status": "OPEN",
      "elapsed_minutes": 46,
      "is_breached": true,
      "requires_escalation": false
    },
    {
      "incident_id": "INC-2002",
      "title": "Lentitud del reporte de cierre",
      "component": "reporting-api",
      "severity": "P2",
      "status": "IN_PROGRESS",
      "elapsed_minutes": 360,
      "is_breached": false,
      "requires_escalation": true
    }
  ]
}
```

**Vacío**:

```json
{ "total_active": 0, "breached_count": 0, "incidents": [] }
```

## Errores

Todos usan `application/problem+json` con `type`, `title`, `status`, `detail`, `code` y `errors[]`.

| HTTP | `code` | Causa |
|---|---|---|
| 422 | `SUMMARY_SOLICITUD_INVALIDA` | Parámetro desconocido o con forma inválida distinta de la fecha de referencia |
| 422 | `SUMMARY_COMPONENTE_DEMASIADO_LARGO` | `component` supera 128 caracteres |
| 422 | `SUMMARY_REFERENCIA_INVALIDA` | Instante no parseable, con zona horaria o valor no admitido |
| 409 | `SUMMARY_REFERENCIA_INCONSISTENTE` | Algún incidente activo tiene `created_at` posterior al instante de referencia |
| 500 | `SUMMARY_ERROR_INTERNO` | Fallo inesperado del servidor; no expone detalles internos |

Una consulta rechazada nunca devuelve totales ni detalle parcial.

## Reglas de paridad

- La CLI produce exactamente el mismo documento JSON (mismas claves y valores) para los mismos datos e instante.
- `reference_time` no se repite en la respuesta; quien compara debe fijarlo explícitamente en ambos canales.
- `GET` es de solo lectura: no modifica incidentes, políticas ni índices.

## Ejemplos de invocación

```bash
curl "http://127.0.0.1:8000/api/v1/incidents/summary"
curl "http://127.0.0.1:8000/api/v1/incidents/summary?component=payments-gateway"
curl "http://127.0.0.1:8000/api/v1/incidents/summary?reference_time=2026-11-20T12:00:00"
```
