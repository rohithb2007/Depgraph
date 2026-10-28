"""Audit the installed environment, excluding only this locally developed project."""

import importlib.metadata
import subprocess
import sys
from pathlib import Path


def main():
    requirements = set()
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        if name.lower().replace("_", "-") == "depgraph-maintainer":
            continue  # Local source is covered by tests/scanning, not a PyPI advisory record.
        requirements.add(f"{name}=={distribution.version}")
    target = Path(".depgraph/audit/requirements.txt")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(sorted(requirements)) + "\n", encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "-r",
            str(target),
            "--no-deps",
            "--disable-pip",
            "--strict",
            "--progress-spinner",
            "off",
            "--cache-dir",
            ".depgraph/audit/cache",
            "--timeout",
            "15",
        ],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
