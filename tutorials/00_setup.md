# 0 · Setup

## 1. Python environment

We use [uv](https://docs.astral.sh/uv/) (fast, reproducible).

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

```bash
uv sync --extra dev --extra dicom
```

```bash
uv run pytest -q
```

All tests run offline against a **simulated Slurm cluster** (`HPC_BACKEND=local`).

## 2. Settings

```bash
cp .env.example .env
```

Everything is configured by environment variables (see `src/medphys_agents/config.py`).
Leave `HPC_BACKEND=local` until tutorial 3.

## 3. SSH to the cluster (for the real-HPC parts)

Agents cannot answer 2FA prompts, so we let *you* authenticate once and the agent reuses
that connection (SSH **ControlMaster**). Add to `~/.ssh/config`:

```
Host mike
    HostName mike.hpc.lsu.edu
    User your_username
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 8h
    ServerAliveInterval 60
```

Open the master connection in a terminal (enter password / 2FA here):

```bash
ssh -fN mike
```

Check it works with no prompt:

```bash
ssh mike hostname
```

Then set `HPC_BACKEND=ssh`, `HPC_HOST=mike`, your `SLURM_ACCOUNT` and `SLURM_PARTITION` in `.env`.
On the cluster, make sure `python3` with `numpy` is available (`HPC_MODULES` lists modules to load).

> Swap `mike.hpc.lsu.edu` for whatever cluster you use — the code only assumes Slurm.

## 4. LLM (optional)

All agents work without an LLM (deterministic fallbacks). With a key, planning,
summaries, and report prose use the model:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

`MEDPHYS_MODEL` accepts any LangChain `provider:model` string (default
`anthropic:claude-opus-5-5`). Use an institution-approved provider for anything sensitive.

## 5. Claude Code

Open this folder in Claude Code (CLI, desktop app or IDE). The skills in `.claude/skills/`
and the notes in `CLAUDE.md` are picked up automatically.
