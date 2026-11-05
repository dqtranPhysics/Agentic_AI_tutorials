# 5 · Agents 3 & 4 — analysis and report

Files: `agents/analysis_agent.py`, `agents/report_agent.py`, `physics/analysis.py`

```
Agent 3:  START → load → metrics → qa_check → plot → END
Agent 4:  START → draft_discussion → assemble → END
```

## Run them on a finished job

```bash
MEDPHYS_LLM=off uv run medphys-agents analyze runs/job_<id>
```

Outputs in that folder: `report.md`, `metrics.json`, `idd_comparison.png`.

## What is computed

| Metric | Meaning |
|---|---|
| R80, R90 | distal depth at 80 % / 90 % of peak; R80 ≈ CSDA range |
| ΔR80 | R80 − CSDA range (Bragg–Kleeman) — a sanity check on the physics |
| DFO 80–20 | distal fall-off width |
| Peak/plateau | D_peak / D(2 cm) |
| σ_rel | batch-method relative uncertainty, mean over D > 50 % D_max (TG-105) |
| γ pass | 1D global gamma 3 %/2 mm, 10 % threshold vs a high-statistics "commissioning" reference |

The QA tolerances live at the top of `analysis_agent.py` and match the `dose-comparison-qa` skill.

## Design lesson: who computes the numbers?

- **Numbers come from code.** Agent 3 has *no* LLM: metrics and QA flags are deterministic
  and unit-testable.
- **Prose comes from the LLM, constrained.** Agent 4 builds the results table in code and asks
  the model only for the discussion, passing the exact metrics and saying *"Use ONLY these
  numbers."* Offline, a template sentence is used.

This split is the single most useful habit for scientific agents: an LLM paraphrasing a
table is fine; an LLM *computing* your R80 is not.

## See a QA flag fire

```bash
MEDPHYS_LLM=off uv run medphys-agents pipeline "70, 120 and 200 MeV with 500 histories" --yes
```

With 500 histories σ_rel exceeds 2 %, and the report recommends how many more histories you
need (σ ∝ 1/√N). Notice how poor statistics also wreck the gamma pass rate at 200 MeV —
noisy peak normalization shifts the whole curve.

## Exercises

1. Add a 2D/3D gamma using the skill's `compare_dose.py` (import `gamma_index`).
2. Make `qa_check` route conditionally: if σ_rel is too high, loop back to the job agent with
   `histories × factor` (in the pipeline graph).
