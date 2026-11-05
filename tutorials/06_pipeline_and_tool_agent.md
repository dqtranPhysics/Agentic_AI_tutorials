# 6 · The full pipeline, and a tool-calling agent

## Agent 5 — pipeline (`agents/pipeline.py`)

The four agents become **subgraphs** of one parent graph:

```python
g.add_node("connect", connect_agent.build_graph())
g.add_node("job",     job_agent.build_graph(standalone=False))
g.add_node("analyze", analysis_agent.build_graph())
g.add_node("report",  report_agent.build_graph())
```

The parent state is the union of the child states, so keys like `outputs`, `metrics` and
`flags` flow from one subgraph to the next automatically. The approval `interrupt()` inside
the job subgraph pauses the *whole* pipeline (one checkpointer on the parent).

```bash
MEDPHYS_LLM=off uv run medphys-agents pipeline "Proton IDDs at 70, 120 and 200 MeV with 20000 histories"
```

```bash
uv run medphys-agents graph pipeline
```

## Agent 6 — tool-calling research assistant (`agents/tool_agent.py`)

Here the **model chooses** what to do, using three tools:

| Tool | Guardrail |
|---|---|
| `cluster_command(command)` | allowlist of read-only commands; rejects `; \| & > $` etc. |
| `submit_idd_job(energies_mev, histories)` | `HumanInTheLoopMiddleware` pauses for your approval on every call |
| `analyze_and_report(outputs, ...)` | runs Agents 3+4 (deterministic numbers) |

Needs an LLM:

```bash
uv run medphys-agents chat
```

Try:

> *Is the workq partition busy? If not, run 90 and 160 MeV with 30000 histories and tell me
> whether the R80 values agree with the CSDA range.*

Watch it call `cluster_command("sinfo -s")`, propose a job (you approve), then analyze.

## When to use which

| | Workflow (Agents 1–5) | Tool agent (Agent 6) |
|---|---|---|
| Path | fixed by you | chosen by the model |
| Cost / latency | low, predictable | higher, variable |
| Testing | easy (see `tests/`) | needs evals |
| Good for | routine production runs | exploratory questions, ad-hoc ops |

## Guardrails checklist for anything touching a real cluster

- [ ] Read-only by default; spending actions (sbatch, scancel, rm) need human approval.
- [ ] No free-form shell from the model. Allowlist commands, reject operators.
- [ ] Bound every loop (`MAX_POLLS`, model step limits).
- [ ] No PHI in prompts or on the cluster.
- [ ] Log what was submitted (job id, script, provenance.json) so results are reproducible.

## Where next

- Persist checkpoints with `langgraph-checkpoint-sqlite` so long jobs survive restarts.
- Replace the toy workload with TOPAS (skill template) and the 1D gamma with 3D.
- Add the QA → resubmit loop from tutorial 5's exercise.
