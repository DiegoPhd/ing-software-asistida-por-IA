# Contrato CLI · `create` y `sla`

**Comandos**:

```bash
uv run python -m src.adapters.inbound.cli create [opciones]
uv run python -m src.adapters.inbound.cli sla [opciones]
```

## `create`

| Opción | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `--incident-id` | texto | Sí, salvo que venga en `--file` | Único; recortado; no vacío; máximo 64 caracteres |
| `--raw-text` | texto | Sí (`--raw-text`, `--raw-text -` o `--file`) | Texto original; `-` lo lee de la entrada estándar; máximo 10 000 caracteres |
| `--file` | ruta | Alternativa a `--raw-text` | JSON con un único objeto `{incident_id?, raw_text, title?, created_at?}` |
| `--title` | texto | No | Si se omite, se deriva del texto; máximo 200 caracteres |
| `--created-at` | ISO 8601 naive | No | `YYYY-MM-DDTHH:MM:SS[.ffffff]`, separador `T`, sin zona horaria; si se omite, el instante de la solicitud |

`--raw-text` y `--file` son mutuamente excluyentes. Si el archivo trae `incident_id` y también se
indica `--incident-id`, deben coincidir; un desacuerdo es `CREATE_SOLICITUD_INVALIDA` con salida `2`.

**Salida estándar**: el documento JSON de
[incident-created.schema.json](./incident-created.schema.json), idéntico al del canal HTTP para la
misma entrada y el mismo `created_at`.

```bash
uv run python -m src.adapters.inbound.cli create \
  --incident-id INC-3001 \
  --raw-text "Pasarela de pagos caída: ningún comercio puede cobrar con tarjeta." \
  --created-at 2026-11-20T10:00:00
```

## `sla`

| Opción | Tipo | Obligatorio | Regla |
|---|---|---|---|
| `--incident-id` | texto | Sí | Identificador del incidente almacenado |
| `--reference-time` | ISO 8601 naive | No | Instante único de evaluación; si se omite, el instante actual |

**Salida estándar**: el documento JSON de
[sla-evaluation.schema.json](./sla-evaluation.schema.json), idéntico al del canal HTTP para el mismo
incidente y el mismo `reference_time`.

```bash
uv run python -m src.adapters.inbound.cli sla --incident-id INC-3001 --reference-time 2026-11-20T12:00:00
```

## Códigos de salida

| Código | Situación | Canal |
|---|---|---|
| 0 | Operación exitosa, incluido el alta con aviso de duplicados | `stdout` con JSON |
| 2 | Entrada inválida: campo vacío, longitud excedida, fecha mal formada o con zona, campo desconocido | `stderr` con problem+json; `stdout` vacío |
| 1 | Identificador ya existente, incidente inexistente, incoherencia temporal o de datos, fallo inesperado | `stderr` con problem+json o mensaje; sin documento parcial |

**Códigos de error**: los mismos del contrato HTTP (`CREATE_*`, `SLA_*`). La correspondencia es:

| Situación | HTTP | CLI |
|---|---:|---:|
| Entrada inválida (forma o formato) | 422 | 2 |
| Referencia anterior a la creación | 422 | 1 |
| Identificador ya existente | 409 | 1 |
| Datos almacenados incoherentes | 409 | 1 |
| Incidente inexistente | 404 | 1 |

## Datos y paridad

- Se leen y escriben en `DATABASE_URL` (por defecto `sqlite:///:memory:`). Para compartir datos entre
  procesos usa `sqlite:///archivo.db`.
- La CLI y HTTP serializan el mismo modelo con `model_dump(mode="json")`; la prueba de aceptación
  compara los documentos por igualdad estricta, sin comparar saltos de línea ni orden de claves.
- Ningún comando imprime un documento parcial cuando falla.
- `create` usa exactamente `IncidentService.create_incident` y `sla` exactamente
  `IncidentService.evaluate_incident_sla`; la CLI no clasifica, no calcula SLA y no decide
  equivalencias.
