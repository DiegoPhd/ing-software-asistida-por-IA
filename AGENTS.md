# AGENTS.md

> **Normativa:** `docs/constitution.md` consolida los invariantes del dominio, la
> arquitectura hexagonal (ADR-003) y la gobernanza técnica. Este archivo es la guía
> operativa del repositorio; si hay conflicto, prevalece la Constitución.

## What this repo is
`IncidentOps` starter project for ISIA Week 1: a small Python 3.10 + stdlib + `tiktoken` exercise, with SQLite in memory. Each "reto" is a graded exercise, and some bad behavior is deliberate.

## Commands (run from the repo root)
- `uv sync`
- `uv run python -m src.context_audit --symbol evaluate_sla_status` (or `--compare-formats`)
- `uv run python -m src.incident_repository [--records N] [--iterations N]`
- `uv run python -m src.triage_rules`
- `uv run python -m src.sla_calculator`

`[tool.uv] package = false` and all imports are absolute (`from src.models import ...`), so module paths only resolve from the repo root. Ignore the README's `week-1/starter-project` path; this repo root is the starter project.

There is no test suite, linter, formatter, or type checker configured. ADR-002 mentions `tests/test_sla_calculator.py`, but it does not exist. Verify changes by running the relevant module demo and checking the printed values.

## Do not "fix" intentional debt
- `IncidentRepository.get_active_incidents_summary` deliberately does `SELECT *`, filters in Python, and issues an N+1 query per row. It is the Phase 2 refactoring exercise; leave it alone unless the task is that refactor.
- README §3/§4 and `CONTEXT_LOG.md` describe the pre-refactor state. `triage_rules.py` and `sla_calculator.py` are already refactored, so trust the code and ADR-002 over README prose.

## Architecture gotchas
- Domain types are duplicated. `src/sla_calculator.py` defines its own plain-class `Incident`, `SLARule`, `SLAEvaluation`, `SeverityLevel`, and `IncidentStatus`, while `src/models.py` has dataclasses with the same names. `evaluate_sla_status` and `incident_repository` use the `sla_calculator` versions, so editing `models.py` does not change SLA behavior.
- `models.IncidentStatus` omits `IN_PROGRESS`, even though the repository seeds/queries it and `sla_calculator` includes it.
- SLA invariants: P0 60 min and P1 240 min run 24x7; P2 480 min and P3 1440 min count only Mon-Fri 08:00-18:00; holidays are a documented TODO. Escalation triggers at 75% of the allowance, and breach is strictly `elapsed > allowed`.
- Triage processes a batch in `created_at` order so the earliest incident is the original. Duplicates require >= 0.75 `SequenceMatcher` similarity within P0 1 day, P1 2 days, P2 3 days, or P3 4 days.

## Conventions
- Code, docstrings, and docs are in Spanish; keep them that way.
- `CONTEXT_LOG.md` is the graded prompt-engineering log. Do not rewrite or regenerate it as filler.
- ADRs go in `docs/adr/NNN-*.md` using `docs/adr/000-template.md`, including a Mermaid diagram.
- Work lands on `diego.betancourt/reto-N` branches merged by PR into `main`.
- On Windows, accented Spanish output may look like mojibake in the console; set `$env:PYTHONIOENCODING='utf-8'` before trusting the text.
