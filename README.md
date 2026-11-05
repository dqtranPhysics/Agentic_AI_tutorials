# Agentic AI for Medical Physics Research — Tutorials

Hands-on material for our group: **Claude Code skills** that capture how we do common
medical-physics tasks, and **LangGraph agents** that connect to an HPC cluster, submit
Monte Carlo jobs, analyze the output, and write a report.

Everything runs **offline on a simulated Slurm cluster** first, so you can learn the
mechanics without an allocation or API key. Then you point it at a real cluster.

```
                       ┌──────────────── pipeline (Agent 5) ────────────────┐
  "Run 70,120,200 MeV" │ connect ──► job ──► analyze ──► report             │ ──► report.md
                       │ (Agent 1)  (Agent 2) (Agent 3)  (Agent 4)          │     + plot
                       │            ▲ human approval before sbatch          │
                       └────────────────────────────────────────────────────┘
```

## Quick start

```bash
uv sync --extra dev
```

```bash
uv run pytest -q
```

```bash
MEDPHYS_LLM=off uv run medphys-agents pipeline "Proton IDDs at 70, 120 and 200 MeV with 20000 histories"
```

Open the `report.md` path it prints. No API key or cluster needed.

## Tutorials

| # | Tutorial | You learn |
|---|---|---|
| 0 | [Setup](tutorials/00_setup.md) | uv, `.env`, SSH config for the cluster, API key (optional) |
| 1 | [Claude Code skills for medical physics](tutorials/01_skills.md) | The three skills in `.claude/skills/`, how to write your own |
| 2 | [LangGraph in 15 minutes](tutorials/02_langgraph_basics.md) | State, nodes, edges, conditional routing |
| 3 | [Agent 1 — connect to HPC](tutorials/03_connect_agent.md) | Backends, SSH ControlMaster + 2FA, diagnosing failures |
| 4 | [Agent 2 — submit & monitor jobs](tutorials/04_job_agent.md) | Structured LLM output, `interrupt()` approval, polling loops |
| 5 | [Agents 3 & 4 — analysis and report](tutorials/05_analysis_report.md) | Deterministic analysis nodes, LLM-written prose without invented numbers |
| 6 | [The full pipeline + a tool-calling agent](tutorials/06_pipeline_and_tool_agent.md) | Subgraph composition; workflow vs. agent; guardrails |

## Repository layout

```
.claude/skills/                 Claude Code skills (auto-discovered in this repo)
  dicom-rt-inspector/           summarize RT DICOM + PHI check before data leaves the workstation
  slurm-mc-dose-job/            group conventions + templates for MC dose job arrays
  dose-comparison-qa/           gamma / uncertainty / R80 analysis with TG-218 reporting
src/medphys_agents/
  config.py  llm.py  hpc.py     settings, optional LLM, HPC backends (local-sim | ssh)
  physics/toy_mc_dose.py        the workload: toy proton pencil-beam MC (numpy, seconds)
  physics/analysis.py           R80, DFO, uncertainty, 1D gamma, plotting
  agents/connect_agent.py       Agent 1
  agents/job_agent.py           Agent 2
  agents/analysis_agent.py      Agent 3
  agents/report_agent.py        Agent 4
  agents/pipeline.py            Agent 5 (composes 1–4)
  agents/tool_agent.py          Agent 6 (LLM chooses tools; needs API key)
  cli.py                        `medphys-agents` command
tests/                          offline smoke tests
tutorials/                      the lessons
```

## Important: data governance

- **Never** commit or copy identifiable patient data. `*.dcm` and `runs/` are git-ignored;
  use the `dicom-rt-inspector` skill to check for PHI first.
- When an LLM is enabled, prompts are sent to the model provider. The agents only send
  cluster status text and computed metrics — keep it that way for anything clinical, and
  follow your institution's policy on approved AI services.
- The toy MC is a teaching workload, **not** a clinical dose engine.
