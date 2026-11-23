# AGENTS.md

> **Normativa:** `docs/constitution.md` consolida los invariantes del dominio, la
> arquitectura hexagonal (ADR-003) y la gobernanza técnica. Este archivo es la guía
> operativa del repositorio; si hay conflicto, prevalece la Constitución (versión
> **1.1.1**).

## What this repo is
`IncidentOps` starter project for ISIA Week 1: a small Python 3.10 exercise that grew into a hexagonal layout for triage (H001) and the active-incidents summary (H002), with FastAPI + Typer over SQLite. `tiktoken` is used by the context audit. Each "reto" is a graded exercise.

H002 is the Phase 2 refactor that removed the deliberate `SELECT *` / Python-filter / N+1 debt. It migrated the SLA calculation and the duplicated types into `src/domain/` and retired the legacy entry points.

## Commands (run from the repo root)
- `uv sync`
- `uv run pytest`
- `uv run ruff check src/`
- `uv run python -m src.context_audit --symbol evaluate_sla_status` (or `--compare-formats`)
- `uv run python -m src.adapters.inbound.cli triage --incident-id INC-1001 --raw-text "..."` (o `--raw-text -` para `stdin`, `--file` para un único reporte)
- `uv run python -m src.adapters.inbound.cli summary [--component C] [--reference-time 2026-11-20T12:00:00]`
- `uv run uvicorn src.adapters.inbound.api.app:app --reload`
- `uv run python -m src.adapters.outbound.sqlite_repository --records 10000 --iterations 20`
- `uv run python tools/benchmark_summary.py --records 10000 --iterations 20`

`[tool.uv] package = false` and all imports are absolute (`from src.models import ...` only for the retired legacy; new code uses `from src.domain...`), so module paths only resolve from the repo root. Ignore the README's `week-1/starter-project` path; this repo root is the starter project.

Ruff is configured in `pyproject.toml` (`target-version = "py310"`, `select = ["E4", "E7", "E9", "F", "TID"]`) plus nested `ruff.toml` files for the domain, application and inbound boundaries. There is no formatter or type checker configured.

## Do not "fix" remaining intentional debt
- `find_open_duplicates` only returns active candidates of the same component; text similarity and the severity window belong to H003. `duplicate_group_key` remains `null`.
- Local holidays are still not subtracted from the business-hours calculation (ADR-002).
- `legacy/triage_rules.py` is a frozen historical copy: never treat it as a source of truth and never import it.
- README §"Fase 2" and `CONTEXT_LOG.md` describe earlier states. Trust the code, the ADRs and `specs/` over old prose.

## Architecture gotchas
- H002 layout: `src/domain/` (entidades y reglas puras) → `src/application/` (`IncidentService`, `ValidationError`, `DataInconsistencyError`, `IncidentRepositoryPort`) → `src/adapters/inbound/{api,cli.py,summary_contract.py}` and `src/adapters/outbound/{sqlite_repository.py,factory.py}`.
- `src/adapters/outbound/factory.py` is the **only** composition root. It selects the repository from `DATABASE_URL` (absent or `sqlite:///:memory:` → memory; `sqlite:///ruta` → file; other scheme → `ConfigurationError`). `src/composition.py` no longer exists.
- `src/domain/models.py` and `src/domain/sla_calculator.py` are the single source of `Incident`, `IncidentStatus`, `SLARule`, `SLAEvaluation`, `ActiveIncidentsSummary` and the SLA policy. `src/models.py` and `src/sla_calculator.py` were retired; do not recreate them.
- `SLA_POLICY_TABLE` is a `MappingProxyType`; `SLAEvaluation` and the summary are `dataclass(frozen=True)`. The domain rejects timezone-aware datetimes with `TemporalInconsistencyError`.
- The SQLite adapter never calculates SLA and never sorts: it emits one `SELECT` with explicit columns, `INNER JOIN sla_policies`, active-status filter and an optional `component = ?`. The filtered variant uses `idx_incidents_component_status`; `(? IS NULL OR component = ?)` degrades to a table scan, so both SQL variants exist.
- `GET /api/v1/incidents/summary` and `cli summary` share `src/adapters/inbound/summary_contract.py`. The CLI must not import `src.adapters.inbound.api` (Ruff `TID251` enforces it).
- Error codes are prefixed by route: `TRIAGE_*` for the triage endpoint, `SUMMARY_*` for the summary. Temporal incoherence is `409 SUMMARY_REFERENCIA_INCONSISTENTE` in HTTP and exit code `1` in the CLI; invalid input is `422` / exit `2`.
- `reference_time` is naive ISO 8601 `YYYY-MM-DDTHH:MM:SS[.ffffff]`, `T` separator only. The service resolves `datetime.now()` once when it is omitted.
- SLA invariants: P0 60 min and P1 240 min run 24x7; P2 480 min and P3 1440 min count only Mon-Fri 08:00-18:00; holidays are a documented TODO. Escalation triggers at `int(allowed * 0.75)`, requires an active state, and breach is strictly `elapsed > allowed`.
- Triage (H001) is stateless and processes a single report: no clock, no persistence, no batch. Impact-based severity takes precedence P0 → P1 → P2 → P3 with P2 as default; component/team come from the closed catalog in `src/domain/severity.py`, and the order of component checks is part of the contract (payments beats gateway).

## Conventions
- Code, docstrings, and docs are in Spanish; keep them that way.
- `CONTEXT_LOG.md` is the graded prompt-engineering log. Do not rewrite or regenerate it as filler.
- ADRs go in `docs/adr/NNN-*.md` using `docs/adr/000-template.md`, including a Mermaid diagram. ADR-005 records the H002 topology, the single port and the factory.
- Work lands on `diego.betancourt/reto-N` branches merged by PR into `main`.
- On Windows, accented Spanish output may look like mojibake in the console; set `$env:PYTHONIOENCODING='utf-8'` before trusting the text.
