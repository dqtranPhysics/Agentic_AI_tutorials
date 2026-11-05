"""Settings, read from environment variables (optionally from a local .env file).

Copy `.env.example` to `.env` and edit. Nothing here is secret except an API key,
and `.env` is git-ignored.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
RUNS_DIR = REPO_ROOT / "runs"


def _load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Tiny .env loader (KEY=VALUE lines) so we don't need python-dotenv."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass
class Settings:
    # "local" = simulated Slurm on your laptop (default, safe for learning)
    # "ssh"   = real Slurm cluster over SSH
    hpc_backend: str = field(default_factory=lambda: os.getenv("HPC_BACKEND", "local"))
    hpc_host: str = field(default_factory=lambda: os.getenv("HPC_HOST", ""))  # ssh alias, e.g. "mike"
    hpc_workdir: str = field(default_factory=lambda: os.getenv("HPC_WORKDIR", "$HOME/medphys_agents"))
    hpc_python: str = field(default_factory=lambda: os.getenv("HPC_PYTHON", "python3"))
    hpc_modules: str = field(default_factory=lambda: os.getenv("HPC_MODULES", ""))  # "python/3.11 gcc"
    slurm_account: str = field(default_factory=lambda: os.getenv("SLURM_ACCOUNT", "my_allocation"))
    slurm_partition: str = field(default_factory=lambda: os.getenv("SLURM_PARTITION", "workq"))
    poll_seconds: float = field(default_factory=lambda: float(os.getenv("POLL_SECONDS", "5")))
    max_polls: int = field(default_factory=lambda: int(os.getenv("MAX_POLLS", "720")))
    # LLM: any langchain "provider:model" string; MEDPHYS_LLM=off forces offline mode
    model: str = field(default_factory=lambda: os.getenv("MEDPHYS_MODEL", "anthropic:claude-opus-5-5"))
    llm_mode: str = field(default_factory=lambda: os.getenv("MEDPHYS_LLM", "auto"))


def get_settings() -> Settings:
    return Settings()
