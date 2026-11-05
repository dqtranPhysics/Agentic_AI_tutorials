# 3 · Agent 1 — connect to the HPC system

File: `src/medphys_agents/agents/connect_agent.py`

```
START → check_connection ─ok──► probe_cluster → summarize → END
                         └fail─► diagnose → END
```

## Run it (simulated cluster)

```bash
MEDPHYS_LLM=off uv run medphys-agents connect
```

You'll see fake-but-realistic `sinfo`, `squeue`, and allocation output from `LocalSlurm`.

## How the HPC layer works (`hpc.py`)

Agents never call `ssh` directly; they use a 5-method backend:
`run`, `put`, `get`, `submit`, `status` (+ `cancel`). Two implementations:

- **`LocalSlurm`** — runs array tasks as local subprocesses and fakes read-only Slurm
  commands. Great for teaching and unit tests.
- **`SSHSlurm`** — wraps `ssh`/`scp` with `ControlMaster`, so after *you* authenticate once
  (`ssh -fN mike`), every agent command reuses that socket — no 2FA prompts mid-graph.

Swapping in a different transport (Globus Compute, a facility REST API, Paramiko) means
writing one class with these methods; no agent code changes.

## Run it on the real cluster

```bash
ssh -fN mike
```

```bash
HPC_BACKEND=ssh HPC_HOST=mike uv run medphys-agents connect
```

Break it on purpose (`HPC_HOST=nonexistent`) to see the `diagnose` branch.

## With an LLM

Set `ANTHROPIC_API_KEY` and drop `MEDPHYS_LLM=off`: `summarize` turns raw command output
into a few bullet points. Notice the system prompt: *"Do not invent numbers not in the data."*

## Exercises

1. Add a probe for your scratch quota (e.g. `showquota` or `lfs quota -u $USER /work`).
2. Add a conditional edge: if the allocation balance is below a threshold, route to a
   `warn_low_balance` node.
