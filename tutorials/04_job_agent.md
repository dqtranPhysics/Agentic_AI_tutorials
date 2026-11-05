# 4 · Agent 2 — submit and monitor a Monte Carlo job

File: `src/medphys_agents/agents/job_agent.py`

```
START → plan → render → approve ─yes─► submit → monitor ─done─► collect → END
                           └no──► END              ↺ (poll loop)
```

## The workload

`physics/toy_mc_dose.py` — a numpy Monte Carlo of a proton pencil beam in water
(Bragg–Kleeman slowing down, range straggling, nuclear losses, batch-method uncertainty).
It takes seconds, so the whole loop is fast. To run TOPAS instead, change `RUN_COMMAND`
in `render()` and use the TOPAS template from the `slurm-mc-dose-job` skill.

## Run it

```bash
MEDPHYS_LLM=off uv run medphys-agents submit "Run 100 and 150 MeV with 20000 histories"
```

The graph **pauses** and prints the rendered sbatch script. Type `yes` to submit. It then
polls until all array tasks finish and copies results to `runs/job_<id>/`.

## Key ideas in the code

**1. Structured output from natural language (`plan`).**
`llm_structured(prompt, JobSpec)` asks the model to fill a Pydantic schema, so downstream
code gets typed, validated fields (energies within 30–250 MeV, histories ≥ 100). Offline,
a regex fallback does the same job — always have a fallback for anything the pipeline
depends on.

**2. Templates, not LLM-written scripts (`render`).**
The sbatch script comes from the skill's template. LLMs are good at extracting *what* you
want; the *how* (seeds, provenance, throttles) should be reviewed code.

**3. Human-in-the-loop (`approve`).**

```python
answer = interrupt({"question": "Submit this job?", "script": state["script"]})
```

`interrupt()` saves the state through the **checkpointer** and returns control to the
caller. The CLI shows the payload, asks you, then resumes with
`graph.invoke(Command(resume="yes"), config)` (see `cli.py::_run_with_approval`).
With a persistent checkpointer (e.g. SQLite) you could approve hours later from another process.

**4. Polling as a loop (`monitor` → `monitor`).**
A conditional edge routes back to `monitor` until `all_done(states)`; `MAX_POLLS` bounds it.
Set `POLL_SECONDS=30` or more on a real cluster — don't hammer the scheduler.

## On the real cluster

```bash
HPC_BACKEND=ssh uv run medphys-agents submit "Run 70, 120 and 200 MeV with 200000 histories"
```

Check `SLURM_ACCOUNT`, `SLURM_PARTITION`, `HPC_MODULES`, and `HPC_WORKDIR` in `.env` first.
Review the script before typing `yes` — it's your allocation.

## Exercises

1. Add a `pilot` node before `approve` that runs one task with 1 % of the histories and sets
   `walltime` from the measured runtime (the skill's checklist item).
2. Add a `retry_failed` branch: if some tasks FAILED, resubmit only those indices
   (`--array=3,7`).
