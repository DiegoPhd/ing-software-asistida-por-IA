# Contrato CLI · Resumen de Incidentes Activos

**Comando**: `uv run python -m src.adapters.inbound.cli summary [opciones]`

| Opción | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `--component` | texto | No | Comparación exacta, espacios exteriores ignorados; ausente o vacío significa todos; máximo 128 caracteres |
| `--reference-time` | ISO 8601 naive | No | Instante único de evaluación, sin zona horaria; si se omite, el instante actual |

Se adopta `--reference-time` (con guion) por consistencia con `--incident-id` y `--raw-text`; el borrador `--referencetime` se descarta.

**Salida estándar**: el documento JSON de [summary.schema.json](./summary.schema.json), idéntico al del canal HTTP para los mismos datos e instante. Se imprime con sangría legible y sin escapar acentos.

```bash
uv run python -m src.adapters.inbound.cli summary
uv run python -m src.adapters.inbound.cli summary --component payments-gateway
uv run python -m src.adapters.inbound.cli summary --reference-time 2026-11-20T12:00:00
```

**Datos**: se leen de `DATABASE_URL` (por defecto `sqlite:///:memory:`). Una base en memoria recién creada no contiene incidentes y devuelve el resumen vacío.

## Códigos de salida

| Código | Situación | Canal |
|---|---|---|
| 0 | Consulta exitosa, incluido el resultado vacío | `stdout` con JSON |
| 2 | Entrada inválida: componente demasiado largo, fecha no parseable o con zona | `stderr` con problem+json; `stdout` vacío |
| 1 | Dato inconsistente (creación posterior al instante) o fallo inesperado | `stderr`; sin resumen parcial |

**Códigos de error**: los mismos del contrato HTTP (`SUMMARY_COMPONENTE_DEMASIADO_LARGO`, `SUMMARY_REFERENCIA_INVALIDA`, `SUMMARY_SOLICITUD_INVALIDA`, `SUMMARY_REFERENCIA_INCONSISTENTE`, `SUMMARY_ERROR_INTERNO`).

## Paridad verificable

La prueba de aceptación siembra una base temporal, invoca la CLI y el endpoint con el mismo `reference_time`, parsea ambos documentos y los compara por igualdad estricta. No se comparan formatos ni saltos de línea.
