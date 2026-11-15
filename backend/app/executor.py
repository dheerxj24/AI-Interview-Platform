import os
import resource
import subprocess
import sys
import time

from .config import settings

SANDBOX_IMAGE = "interview-sandbox:latest"


def _limit_child() -> None:
    # Runs in the child process before exec (POSIX only).
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))


def execute(code: str, stdin: str, timeout_s: float = 5.0) -> dict:
    if settings.executor == "docker":
        cmd = [
            "docker", "run", "--rm", "-i",
            "--network", "none",
            "--memory", "128m",
            "--cpus", "0.5",
            "--pids-limit", "64",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=16m",
            "--user", "65534:65534",
            SANDBOX_IMAGE,
            "python", "-I", "-c", code,
        ]
        preexec = None
    else:
        cmd = [sys.executable, "-I", "-c", code]
        preexec = _limit_child if os.name == "posix" else None

    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            preexec_fn=preexec,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "Time limit exceeded", "runtime_ms": int(timeout_s * 1000)}

    runtime_ms = int((time.perf_counter() - started) * 1000)
    return {
        "ok": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr[-2000:],
        "runtime_ms": runtime_ms,
    }
