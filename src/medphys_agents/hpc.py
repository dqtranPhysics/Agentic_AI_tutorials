"""HPC backends with one small interface the agents use.

    run(cmd)            -> CommandResult      run a shell command on the login node
    put(local, remote)  -> None               copy a file to the cluster
    get(remote, local)  -> None               copy a file/folder back
    submit(script, workdir) -> job_id         sbatch
    status(job_id)      -> {task: STATE}      squeue / sacct
    cancel(job_id)

Two implementations:

* LocalSlurm  — simulates a Slurm cluster on your laptop (subprocesses + fake sinfo/squeue).
                Default, so everyone can run the tutorials without an allocation.
* SSHSlurm    — a real cluster through your ~/.ssh/config. Uses SSH ControlMaster so you
                authenticate (password + 2FA/Duo) ONCE and the agent reuses that connection.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .config import RUNS_DIR, Settings, get_settings

TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"}


@dataclass
class CommandResult:
    cmd: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def parse_array_range(script: str) -> list[int]:
    """'#SBATCH --array=0-4%2' -> [0,1,2,3,4]; also handles '1,3,5'."""
    m = re.search(r"#SBATCH\s+--array=([0-9,\-]+)", script)
    if not m:
        return [0]
    ids: list[int] = []
    for part in m.group(1).split(","):
        if "-" in part:
            a, b = part.split("-")
            ids.extend(range(int(a), int(b) + 1))
        else:
            ids.append(int(part))
    return ids


# --------------------------------------------------------------------------- local
class LocalSlurm:
    """A pretend Slurm cluster. Jobs run as local subprocesses (a few in parallel)."""

    name = "local-sim"
    _jobs: dict[str, dict] = {}  # class-level so all graph nodes see the same "cluster"

    def __init__(self, settings: Settings | None = None, max_parallel: int = 4):
        self.s = settings or get_settings()
        self.max_parallel = max_parallel
        self.root = RUNS_DIR / "local_cluster"
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def workdir(self) -> str:
        return str(self.root)

    @property
    def python(self) -> str:
        return sys.executable

    # Fake outputs for the read-only Slurm commands, so tutorials look realistic.
    def _fake(self, cmd: str) -> str | None:
        user = os.getenv("USER", "you")
        if cmd.startswith("sinfo"):
            return (
                "PARTITION AVAIL  TIMELIMIT   NODES(A/I/O/T) NODELIST\n"
                "workq*       up 3-00:00:00   112/48/4/164 mike[001-164]\n"
                "gpu          up 3-00:00:00     10/2/0/12  mikeg[001-012]\n"
                "single       up 7-00:00:00     30/10/0/40 mikes[001-040]\n"
            )
        if cmd.startswith("squeue"):
            rows = ["JOBID PARTITION NAME USER ST TIME NODES"]
            for jid, j in self._jobs.items():
                for t, st in self._task_states(j).items():
                    if st in ("PENDING", "RUNNING"):
                        rows.append(f"{jid}_{t} workq {j['name']} {user} {st[0]} 0:0{t} 1")
            return "\n".join(rows) + "\n"
        if cmd.startswith(("sshare", "balance", "showquota", "quota")):
            return f"Account {self.s.slurm_account}: 50000.0 SUs allocated, 12345.6 used (simulated)\n"
        return None

    def run(self, cmd: str, timeout: int = 60) -> CommandResult:
        fake = self._fake(cmd.strip())
        if fake is not None:
            return CommandResult(cmd, 0, fake, "")
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout,
                           cwd=self.root)
        return CommandResult(cmd, p.returncode, p.stdout, p.stderr)

    def put(self, local: str | Path, remote: str) -> None:
        dest = Path(remote)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, dest)

    def get(self, remote: str, local: str | Path) -> None:
        src, dst = Path(remote), Path(local)
        if src.resolve() == dst.resolve():
            return
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def submit(self, script: str, workdir: str) -> str:
        job_id = str(int(time.time() * 10) % 10_000_000)
        Path(workdir).mkdir(parents=True, exist_ok=True)
        path = Path(workdir) / f"job_{job_id}.sbatch"
        path.write_text(script)
        name = (re.search(r"--job-name=(\S+)", script) or [None, "job"])[1]
        tasks = {t: None for t in parse_array_range(script)}
        self._jobs[job_id] = {"script": path, "tasks": tasks, "name": name, "workdir": workdir}
        self._launch(job_id)
        return job_id

    def _launch(self, job_id: str) -> None:
        j = self._jobs[job_id]
        running = sum(1 for p in j["tasks"].values() if p is not None and p.poll() is None)
        for t, p in j["tasks"].items():
            if p is None and running < self.max_parallel:
                env = dict(os.environ, SLURM_ARRAY_TASK_ID=str(t), SLURM_ARRAY_JOB_ID=job_id,
                           SLURM_JOB_ID=f"{job_id}_{t}")
                logs = Path(j["workdir"]) / "logs"
                logs.mkdir(parents=True, exist_ok=True)
                out = open(logs / f"{j['name']}_{job_id}_{t}.out", "w")
                j["tasks"][t] = subprocess.Popen(["bash", str(j["script"])], env=env,
                                                 stdout=out, stderr=subprocess.STDOUT)
                running += 1

    def _task_states(self, j: dict) -> dict[int, str]:
        states = {}
        for t, p in j["tasks"].items():
            if p is None:
                states[t] = "PENDING"
            elif p.poll() is None:
                states[t] = "RUNNING"
            else:
                states[t] = "COMPLETED" if p.returncode == 0 else "FAILED"
        return states

    def status(self, job_id: str) -> dict[int, str]:
        if job_id not in self._jobs:
            return {}
        self._launch(job_id)  # start pending tasks as slots free up
        return self._task_states(self._jobs[job_id])

    def cancel(self, job_id: str) -> None:
        for p in self._jobs.get(job_id, {}).get("tasks", {}).values():
            if p is not None and p.poll() is None:
                p.terminate()


# --------------------------------------------------------------------------- ssh
class SSHSlurm:
    """Real Slurm over SSH. HPC_HOST should be a Host alias from ~/.ssh/config.

    First connection opens a master socket (you may be asked for password/2FA once);
    later commands reuse it for ControlPersist minutes, so the agent never re-prompts.
    """

    name = "ssh-slurm"

    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        if not self.s.hpc_host:
            raise ValueError("HPC_HOST is not set (use an alias from ~/.ssh/config)")
        self.host = self.s.hpc_host
        ctl = Path.home() / ".ssh" / "cm-%r@%h:%p"
        self.ssh_opts = ["-o", "ControlMaster=auto", "-o", f"ControlPath={ctl}",
                         "-o", "ControlPersist=30m", "-o", "ServerAliveInterval=60"]
        self._workdir: str | None = None

    @property
    def workdir(self) -> str:
        if self._workdir is None:  # expand $HOME etc. on the remote side once
            self._workdir = self.run(f"echo {self.s.hpc_workdir}").stdout.strip()
        return self._workdir

    @property
    def python(self) -> str:
        return self.s.hpc_python

    def run(self, cmd: str, timeout: int = 120) -> CommandResult:
        remote = f"bash -lc {shlex.quote(cmd)}"
        p = subprocess.run(["ssh", *self.ssh_opts, self.host, remote],
                           capture_output=True, text=True, timeout=timeout)
        return CommandResult(cmd, p.returncode, p.stdout, p.stderr)

    def put(self, local: str | Path, remote: str) -> None:
        self.run(f"mkdir -p {shlex.quote(str(Path(remote).parent))}")
        subprocess.run(["scp", *self.ssh_opts, str(local), f"{self.host}:{remote}"], check=True)

    def get(self, remote: str, local: str | Path) -> None:
        Path(local).mkdir(parents=True, exist_ok=True)
        subprocess.run(["scp", "-r", *self.ssh_opts, f"{self.host}:{remote}/.", str(local)],
                       check=True)

    def submit(self, script: str, workdir: str) -> str:
        name = f"job_{uuid.uuid4().hex[:8]}.sbatch"
        self.run(f"mkdir -p {shlex.quote(workdir)}/logs")
        heredoc = f"cat > {shlex.quote(workdir)}/{name} <<'__SBATCH_EOF__'\n{script}\n__SBATCH_EOF__"
        self.run(heredoc)
        r = self.run(f"cd {shlex.quote(workdir)} && sbatch --parsable {name}")
        if not r.ok:
            raise RuntimeError(f"sbatch failed: {r.stderr.strip()}")
        return r.stdout.strip().split(";")[0]

    def status(self, job_id: str) -> dict[int, str]:
        r = self.run(f"squeue -j {job_id} -h -r -o '%i %T'")
        states: dict[int, str] = {}
        for line in r.stdout.splitlines():
            jid, st = line.split()
            states[int(jid.split("_")[-1]) if "_" in jid else 0] = st
        # Finished tasks leave squeue; ask accounting for them.
        r = self.run(f"sacct -j {job_id} -X -n -P -o JobID,State")
        for line in r.stdout.splitlines():
            jid, st = line.split("|")[:2]
            if "_" in jid and "[" not in jid:
                states.setdefault(int(jid.split("_")[-1]), st.split()[0])
        return states

    def cancel(self, job_id: str) -> None:
        self.run(f"scancel {job_id}")


def get_backend(settings: Settings | None = None):
    s = settings or get_settings()
    if s.hpc_backend == "ssh":
        return SSHSlurm(s)
    return LocalSlurm(s)


def all_done(states: dict[int, str]) -> bool:
    return bool(states) and all(st in TERMINAL_STATES for st in states.values())
