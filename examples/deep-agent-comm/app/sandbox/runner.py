"""L4 — Sandbox. Runs LLM-generated Python in an isolated subprocess
(-I: isolated mode, ignores user site-packages and env vars), cwd locked to a
per-job scratch dir, 30s timeout.

v1 limitation (accepted, same class as the Node port's): the OS does not
restrict filesystem or network for the child. Containment is cwd + isolated
mode + timeout. Move to Docker/E2B when code-exec risk grows."""

import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ..config import SCRATCH_DIR

TIMEOUT_S = 30


@dataclass
class SandboxResult:
    success: bool
    stdout: str
    stderr: str
    files: list[str] = field(default_factory=list)   # files in job dir after run
    job_dir: str = ""


def run_in_sandbox(code: str, input_files: list[str] | None = None) -> SandboxResult:
    job_dir = SCRATCH_DIR / "jobs" / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)

    for f in input_files or []:
        src = Path(f)
        if src.exists():
            shutil.copyfile(src, job_dir / src.name)

    script_path = job_dir / "script.py"
    script_path.write_text(code, encoding="utf-8")

    try:
        proc = subprocess.run(
            [sys.executable, "-I", str(script_path)],
            cwd=job_dir,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
        exit_code = proc.returncode
        stdout, stderr = proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        exit_code = 1
        stdout = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = f"Timed out after {TIMEOUT_S}s"

    files = [str(p) for p in job_dir.iterdir() if p.name != "script.py"]
    return SandboxResult(
        success=exit_code == 0,
        stdout=stdout[:8000],
        stderr=stderr[:4000],
        files=files,
        job_dir=str(job_dir),
    )
