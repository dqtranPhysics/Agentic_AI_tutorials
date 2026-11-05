# Project notes for Claude

Tutorial repo for a medical physics research group: Claude Code skills (`.claude/skills/`)
and LangGraph agents (`src/medphys_agents/`) for HPC Monte Carlo workflows.

- Env: `uv sync --extra dev`; tests: `uv run pytest -q` (offline, simulated Slurm).
- Run agents offline with `MEDPHYS_LLM=off`; real cluster with `HPC_BACKEND=ssh` + `.env`.
- Never print or commit patient-identifying DICOM data; check with the `dicom-rt-inspector` skill.
- Ask before any `sbatch` on a real cluster — it spends the group's allocation.
- Keep agent code simple and commented: the audience is physicists learning agents.
