"""Disposable Python environments and bounded commands for trusted repositories."""

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def execute(command, cwd, timeout=180, env=None):
    started = time.time()
    kwargs = (
        {"start_new_session": True}
        if os.name != "nt"
        else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    )
    # Spool output to disk so a noisy target cannot exhaust server memory.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=out, stderr=err, **kwargs)
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                if process.poll() is None:
                    process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        outputs = []
        for stream in (out, err):
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 24000))
            outputs.append(stream.read().decode("utf-8", errors="replace"))
    return {
        "command": command,
        "return_code": process.returncode,
        "timed_out": timed_out,
        "duration": round(time.time() - started, 3),
        "stdout": outputs[0],
        "stderr": outputs[1],
    }


class VenvRunner:
    def __init__(self, timeout=180):
        self.timeout = timeout

    def validate(self, repo: Path):
        with tempfile.TemporaryDirectory(prefix="depgraph-env-") as folder:
            # Strip common interpreter and credential variables from target execution.
            env = {
                k: v
                for k, v in os.environ.items()
                if not any(word in k.upper() for word in ("TOKEN", "SECRET", "PASSWORD", "API_KEY"))
                and k not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
            }
            commands = []
            python = str(Path(folder) / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
            steps = [
                ("environment", [sys.executable, "-m", "venv", folder]),
                (
                    "install",
                    [
                        python,
                        "-m",
                        "pip",
                        "install",
                        "--disable-pip-version-check",
                        "-r",
                        "requirements.txt",
                        "pytest>=8,<10",
                    ],
                ),
                ("resolve", [python, "-m", "pip", "check"]),
                ("test", [python, "-m", "pytest", "-q", "--tb=short"]),
                ("freeze", [python, "-m", "pip", "freeze", "--all"]),
            ]
            for stage, command in steps:
                result = execute(command, repo, self.timeout, env)
                result["stage"] = stage
                commands.append(result)
                if result["return_code"] != 0 or result["timed_out"]:
                    return {
                        "passed": False,
                        "stage": "timeout" if result["timed_out"] else stage,
                        "failed_stage": stage,
                        "commands": commands,
                    }
            return {"passed": True, "stage": "test", "commands": commands}
