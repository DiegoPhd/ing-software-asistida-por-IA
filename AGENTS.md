# AGENTS.md

> **Normativa:** `docs/constitution.md` consolida los invariantes del dominio, la
> arquitectura hexagonal (ADR-003) y la gobernanza técnica. Este archivo es la guía
> operativa del repositorio; si hay conflicto, prevalece la Constitución (versión
> **1.1.1**).

## What this repo is
`IncidentOps` starter project for ISIA Week 1: a small Python 3.10 exercise that grew into a hexagonal layout for triage (H001), the active-incidents summary (H002) and the persistent lifecycle with duplicates and per-incident SLA (H003), with FastAPI + Typer over SQLite. `tiktoken` is used by the context audit. Each "reto" is a graded exercise.

H002 is the Phase 2 refactor that removed the deliberate `SELECT *` / Python-filter / N+1 debt. It migrated the SLA calculation and the duplicated types into `src/domain/` and retired the legacy entry points.

H003 adds `IncidentService.create_incident` and `IncidentService.evaluate_incident_sla`, the `ClockPort`/`SystemClock` pair, duplicate detection in `src/domain/triage_rules.py`, `SLAEvaluationDetail`, the shared `inbound/lifecycle_contract.py` and `inbound/temporal_contract.py`, and the strict `INSERT` that rejects an existing identifier.

## Commands (run from the repo root)
- `uv sync`
- `uv run pytest`
- `uv run ruff check src/`
- `uv run python -m src.context_audit --symbol evaluate_sla_status` (or `--compare-formats`)
- `uv run python -m src.adapters.inbound.cli triage --incident-id INC-1001 --raw-text "..."` (o `--raw-text -` para `stdin`, `--file` para un único reporte)
- `uv run python -m src.adapters.inbound.cli summary [--component C] [--reference-time 2026-11-20T12:00:00]`
- `uv run python -m src.adapters.inbound.cli create --incident-id INC-1001 --raw-text "..." [--title T] [--created-at 2026-11-20T10:00:00]`
- `uv run python -m src.adapters.inbound.cli sla --incident-id INC-1001 [--reference-time 2026-11-20T12:00:00]`
- `uv run uvicorn src.adapters.inbound.api.app:app --reload`
- `uv run python -m src.adapters.outbound.sqlite_repository --records 10000 --iterations 20`
- `uv run python tools/benchmark_summary.py --records 10000 --iterations 20`

`[tool.uv] package = false` and all imports are absolute (`from src.models import ...` only for the retired legacy; new code uses `from src.domain...`), so module paths only resolve from the repo root. Ignore the README's `week-1/starter-project` path; this repo root is the starter project.

Ruff is configured in `pyproject.toml` (`target-version = "py310"`, `select = ["E4", "E7", "E9", "F", "TID"]`) plus nested `ruff.toml` files for the domain, application and inbound boundaries. There is no formatter or type checker configured.

## Do not "fix" remaining intentional debt
- `find_open_duplicates` only applies the structural filter (active, same component, different id); similarity and the severity window are domain rules in `assess_duplicates`, never SQL. Do not push them into the adapter.
- Duplicate alerts never merge, re-key or modify previous incidents; `duplicate_group_key` is resolved by the domain and inherited from the oldest original.
- The per-component lock only serializes within a single process; do not add a distributed lock or replica coordination (ADR-006).
- Local holidays are still not subtracted from the business-hours calculation (ADR-002).
- `legacy/triage_rules.py` is a frozen historical copy: never treat it as a source of truth and never import it.
- README §"Fase 2" and `CONTEXT_LOG.md` describe earlier states. Trust the code, the ADRs and `specs/` over old prose.

## Architecture gotchas
- H003 layout: `src/domain/` (entidades y reglas puras) → `src/application/` (`IncidentService`, `ValidationError`, `DataInconsistencyError`, `IncidentAlreadyExistsError`, `IncidentNotFoundError`, `ClockPort`, `IncidentRepositoryPort`) → `src/adapters/inbound/{api,cli.py,summary_contract.py,temporal_contract.py,lifecycle_contract.py}` and `src/adapters/outbound/{sqlite_repository.py,system_clock.py,factory.py}`.
- `src/adapters/outbound/factory.py` is the **only** composition root. It selects the repository from `DATABASE_URL` (absent or `sqlite:///:memory:` → memory; `sqlite:///ruta` → file; other scheme → `ConfigurationError`) and injects `SystemClock` through `ClockPort`. `src/composition.py` no longer exists.
- `src/domain/models.py` and `src/domain/sla_calculator.py` are the single source of `Incident`, `IncidentStatus`, `SLARule`, `SLAEvaluation`, `SLAEvaluationDetail`, `ActiveIncidentsSummary`, `derivar_titulo` and the SLA policy. `src/models.py` and `src/sla_calculator.py` were retired; do not recreate them.
- `SLA_POLICY_TABLE` is a `MappingProxyType`; `SLAEvaluation`, `SLAEvaluationDetail`, `DuplicateAssessment` and the summary are `dataclass(frozen=True)`. `validar_instante_naive`, `resolver_ventana_temporal` and `evaluate_sla_detail` are the only temporal normalisation; `evaluate_sla_status` keeps its H002 signature and arithmetic.
- The SQLite adapter never calculates SLA, similarity or duplicate keys and never sorts: it emits one `SELECT` with explicit columns, `INNER JOIN sla_policies`, active-status filter and an optional `component = ?`. The filtered variant uses `idx_incidents_component_status`; `(? IS NULL OR component = ?)` degrades to a table scan, so both SQL variants exist. `save_incident` is a strict `INSERT` (never `REPLACE`) and raises `IncidentAlreadyExistsError`; migration of `raw_text`, `recommended_team` and `duplicate_group_key` is idempotent (`PRAGMA table_info` + `ALTER TABLE`), and `idx_incidents_dup_key (duplicate_group_key, status)` is verified with `EXPLAIN QUERY PLAN`.
- `POST /api/v1/incidents` and `cli create` share `src/adapters/inbound/lifecycle_contract.py`; `GET .../{id}/sla` and `cli sla` share the same contract. `temporal_contract.py` is the only ISO 8601 parser. The CLI must not import `src.adapters.inbound.api` (Ruff `TID251` enforces it).
- Error codes are prefixed by route: `TRIAGE_*`, `SUMMARY_*`, `CREATE_*` for the collection and `SLA_*` for the per-incident audit. `CREATE_ID_CONFLICTO` maps to 409/exit 1; `SLA_INCIDENTE_NO_ENCONTRADO` to 404/exit 1; `SLA_REFERENCIA_INCONSISTENTE` to 422/exit 1; `SLA_DATOS_INCONSISTENTES` to 409/exit 1; invalid input is 422/exit 2. Summary keeps `409 SUMMARY_REFERENCIA_INCONSISTENTE`.
- `created_at` and `reference_time` are naive ISO 8601 `YYYY-MM-DDTHH:MM:SS[.ffffff]`, `T` separator only. The service resolves the current instant once through `ClockPort` when omitted (`datetime.now()` remains the fallback).
- Duplicate rule: active candidates only, same component, distinct id, non-empty `raw_text`; `SequenceMatcher` on lowercased text ≥ 0.75 and `0 <= delta <= ventana(severity del más antiguo)` (P0 1, P1 2, P2 3, P3 4 days). `duplicate_of` lists only previous equivalents in `(created_at, incident_id)` order; the key is the oldest original's `duplicate_group_key or incident_id`. Alerts never modify previous incidents.
- SLA invariants: P0 60 min and P1 240 min run 24x7; P2 480 min and P3 1440 min count only Mon-Fri 08:00-18:00; holidays are a documented TODO. Escalation triggers at `int(allowed * 0.75)`, requires an active state, and breach is strictly `elapsed > allowed`.
- Triage (H001) is stateless and processes a single report: no clock, no persistence, no batch. Impact-based severity takes precedence P0 → P1 → P2 → P3 with P2 as default; component/team come from the closed catalog in `src/domain/severity.py`, and the order of component checks is part of the contract (payments beats gateway).

## Conventions
- Code, docstrings, and docs are in Spanish; keep them that way.
- `CONTEXT_LOG.md` is the graded prompt-engineering log. Do not rewrite or regenerate it as filler.
- ADRs go in `docs/adr/NNN-*.md` using `docs/adr/000-template.md`, including a Mermaid diagram. ADR-005 records the H002 topology, the single port and the factory; ADR-006 records the H003 duplicate rule, the per-component lock, `ClockPort` and the strict `INSERT`.
- Work lands on actual branch branches merged by PR into `main`.
- On Windows, accented Spanish output may look like mojibake in the console; set `$env:PYTHONIOENCODING='utf-8'` before trusting the text.
