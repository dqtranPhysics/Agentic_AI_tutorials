"""Optional LLM.

Every agent in this repo works WITHOUT an LLM (deterministic fallbacks), so colleagues can
run the tutorials offline and see the graph mechanics first. When an API key is available,
the same nodes use the model for planning, summarizing, and writing.
"""

from __future__ import annotations

import os
from functools import lru_cache

from .config import get_settings


@lru_cache(maxsize=1)
def get_llm():
    """Return a LangChain chat model, or None when running offline."""
    s = get_settings()
    if s.llm_mode.lower() == "off":
        return None
    if s.model.startswith("anthropic:") and not (
        os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    ):
        return None
    try:
        from langchain.chat_models import init_chat_model

        return init_chat_model(s.model, max_tokens=8000)
    except Exception as exc:  # missing provider package, bad model string, ...
        print(f"[llm] could not initialise {s.model!r}: {exc}; continuing offline")
        return None


def llm_text(prompt: str, system: str = "", fallback: str = "") -> str:
    """One-shot text completion with a fallback string when offline or on error."""
    llm = get_llm()
    if llm is None:
        return fallback
    msgs = ([("system", system)] if system else []) + [("user", prompt)]
    try:
        out = llm.invoke(msgs)
        return out.text if hasattr(out, "text") else str(out.content)
    except Exception as exc:
        print(f"[llm] call failed ({exc.__class__.__name__}); using fallback")
        return fallback


def llm_structured(prompt: str, schema, system: str = ""):
    """Structured output into a Pydantic schema; returns None when offline or on error.

    Uses method="json_schema" (native structured outputs) — current Claude models reject
    forced tool calls, which the older "function_calling" method relies on.
    """
    llm = get_llm()
    if llm is None:
        return None
    msgs = ([("system", system)] if system else []) + [("user", prompt)]
    try:
        return llm.with_structured_output(schema, method="json_schema").invoke(msgs)
    except Exception as exc:
        print(f"[llm] structured call failed ({exc.__class__.__name__}); using fallback")
        return None
