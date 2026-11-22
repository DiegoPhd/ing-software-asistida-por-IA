# Legado congelado

Este directorio conserva copias históricas de módulos que ya no forman parte del
sistema ejecutable. **No son fuente de verdad y no deben importarse.**

## `triage_rules.py`

- Copia del motor de triaje anterior a H001 (Semana 1).
- Contiene reglas de duplicados que en H001 **no** están implementadas: la
  detección de duplicados pertenece a H003.
- Su `duplicate_group_key` sale de la primera coincidencia encontrada y no del
  original más antiguo, por lo que **no cumple** la Constitución §1.4.
- Imprime trazas en `stdout` (`[CLASSIFY]`, `[BATCH]`, `[DUPLICATE_DETECTED]`) y
  usa `datetime.now()` implícito, ambos prohibidos en el dominio.
- Su salida sobre `data/sample_incidents.json` puede diferir de la del servicio
  actual; la referencia vigente es `src/domain/triage.py` y la suite `tests/`.

Se conserva únicamente como evidencia del punto de partida. Cualquier intento de
ejecutarlo puede fallar porque `src/models.py` ya no declara `TriageResult`.
