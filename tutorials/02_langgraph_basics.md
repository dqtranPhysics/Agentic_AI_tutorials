# 2 · LangGraph in 15 minutes

LangGraph models an agent as a **graph**: a shared **state** dict flows through **nodes**
(plain Python functions) connected by **edges**. That's it.

```python
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class State(TypedDict, total=False):
    energy_mev: float
    range_cm: float
    verdict: str

def compute_range(state: State) -> State:
    return {"range_cm": 0.0022 * state["energy_mev"] ** 1.77}   # Bragg–Kleeman

def deep(state: State) -> State:
    return {"verdict": "deep-seated target"}

def shallow(state: State) -> State:
    return {"verdict": "shallow target"}

def route(state: State) -> str:                                 # conditional edge
    return "deep" if state["range_cm"] > 15 else "shallow"

g = StateGraph(State)
g.add_node("compute_range", compute_range)
g.add_node("deep", deep)
g.add_node("shallow", shallow)
g.add_edge(START, "compute_range")
g.add_conditional_edges("compute_range", route, ["deep", "shallow"])
g.add_edge("deep", END)
g.add_edge("shallow", END)
app = g.compile()

print(app.invoke({"energy_mev": 180}))
# {'energy_mev': 180, 'range_cm': 21.59..., 'verdict': 'deep-seated target'}
```

Save as `scratch.py` and run `uv run python scratch.py`.

## The five ideas you need

| Idea | In code | Used in our agents for |
|---|---|---|
| **State** | `TypedDict`; nodes return *partial updates* | job id, task states, metrics, flags |
| **Node** | any function `state -> dict` | ssh command, sbatch, numpy analysis, LLM call |
| **Conditional edge** | `add_conditional_edges(node, fn, [targets])` | connected? approved? all tasks done? |
| **Loop** | an edge back to the same node | polling `squeue` until the job finishes |
| **Interrupt + checkpointer** | `interrupt(payload)`, `compile(checkpointer=...)`, resume with `Command(resume=...)` | human approval before spending allocation |

## Workflow vs. agent

- A **workflow** is a graph *you* drew: predictable, testable, cheap. LLMs fill in steps
  (parse a request, write prose). Agents 1–5 here are workflows.
- An **agent** lets the *model* pick the next step from a set of tools in a loop.
  Flexible, but harder to bound. Agent 6 is one, with guardrails.

Rule of thumb for research computing: **start with a workflow**; only let the model choose
actions where the path genuinely can't be known in advance.

## See our graphs

```bash
uv run medphys-agents graph job
```

Paste the output into <https://mermaid.live> to view it.
