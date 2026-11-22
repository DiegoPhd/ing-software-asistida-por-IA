# AGENTS.md

> **Normativa:** `docs/constitution.md` consolida los invariantes del dominio, la
> arquitectura hexagonal (ADR-003) y la gobernanza técnica. Este archivo es la guía
> operativa del repositorio; si hay conflicto, prevalece la Constitución.

## What this repo is
`IncidentOps` starter project for ISIA Week 1: a small Python 3.10 exercise that grew into a hexagonal layout for triage (FastAPI + Typer) while SQLite, SLA and the repository remain legacy. `tiktoken` is used by the context audit. Each "reto" is a graded exercise, and some bad behavior is deliberate.

## Commands (run from the repo root)
- `uv sync`
- `uv run pytest`
- `uv run python -m src.context_audit --symbol evaluate_sla_status` (or `--compare-formats`)
- `uv run python -m src.incident_repository [--records N] [--iterations N]`
- `uv run python -m src.sla_calculator`
- `uv run python -m src.adapters.inbound.cli triage --incident-id INC-1001 --raw-text "..."` (o `--raw-text -` para `stdin`, `--file` para un único reporte)
- `uv run uvicorn src.adapters.inbound.api.app:app --reload`

`[tool.uv] package = false` and all imports are absolute (`from src.models import ...`), so module paths only resolve from the repo root. Ignore the README's `week-1/starter-project` path; this repo root is the starter project.

There is a `pytest` suite in `tests/` for the triage capability (H001): `uv run pytest`. There is still no linter, formatter, or type checker configured. ADR-002 mentions `tests/test_sla_calculator.py`, but it does not exist. For SLA and the repository, verify changes by running the module demo and checking the printed values.

## Do not "fix" intentional debt
- `IncidentRepository.get_active_incidents_summary` deliberately does `SELECT *`, filters in Python, and issues an N+1 query per row. It is the Phase 2 refactoring exercise; leave it alone unless the task is that refactor.
- README §3/§4 and `CONTEXT_LOG.md` describe the pre-refactor state. `sla_calculator.py` and the H001 triage capability are already refactored, so trust the code and the ADRs over README prose. `legacy/triage_rules.py` is a frozen historical copy: never treat it as a source of truth and never import it.

## Architecture gotchas
- H001 layout: `src/domain/` (reglas puras) → `src/application/services.py` (`IncidentService`, `ValidationError`) → `src/adapters/inbound/{api,cli.py}`. `src/composition.py` es el único punto que construye clases concretas.
- SLA types are still duplicated. `src/sla_calculator.py` defines its own plain-class `Incident`, `SLARule`, `SLAEvaluation`, `SeverityLevel`, and `IncidentStatus`, while `src/models.py` keeps dataclasses with the same names. `evaluate_sla_status` and `incident_repository` use the `sla_calculator` versions, so editing `models.py` does not change SLA behavior. Triage types are no longer duplicated: `TriageResult` lives only in `src/domain/triage.py`, and `src/models.py` re-exports `SeverityLevel` from `src/domain/severity.py`.
- `models.IncidentStatus` omits `IN_PROGRESS`, even though the repository seeds/queries it and `sla_calculator` includes it.
- SLA invariants: P0 60 min and P1 240 min run 24x7; P2 480 min and P3 1440 min count only Mon-Fri 08:00-18:00; holidays are a documented TODO. Escalation triggers at 75% of the allowance, and breach is strictly `elapsed > allowed`.
- Triage (H001) is stateless and processes a single report: no clock, no persistence, no batch. Impact-based severity takes precedence P0 → P1 → P2 → P3 with P2 as default; component/team come from the closed catalog in `src/domain/severity.py`, and the order of component checks is part of the contract (payments beats gateway). Duplicate detection (`SequenceMatcher` ≥ 0.75 within P0 1 day, P1 2 days, P2 3 days, P3 4 days) belongs to H003; until then `duplicate_group_key` is always `null`.

## Conventions
- Code, docstrings, and docs are in Spanish; keep them that way.
- `CONTEXT_LOG.md` is the graded prompt-engineering log. Do not rewrite or regenerate it as filler.
- ADRs go in `docs/adr/NNN-*.md` using `docs/adr/000-template.md`, including a Mermaid diagram.
- Work lands on `diego.betancourt/reto-N` branches merged by PR into `main`.
- On Windows, accented Spanish output may look like mojibake in the console; set `$env:PYTHONIOENCODING='utf-8'` before trusting the text.
