"""
run_tests tool.

Runs the target repository in a fresh virtual environment.

The target execution environment is pinned to Python 3.11 so that
the demo remains reproducible even when DepGraph itself is running
under a newer Python version.

The result distinguishes:

- dependency installation failure
- test failure
- successful tests
- timeout

This prevents the agent from asking Gemini to diagnose application
code when the dependency environment itself could not be installed.
"""

import subprocess
import os
import shutil
from dataclasses import dataclass


@dataclass
class TestResult:
    passed: bool
    return_code: int
    stdout: str
    stderr: str
    stage: str  # "install", "test", or "timeout"


def create_test_venv(venv_path: str) -> None:
    """
    Create a fresh Python 3.11 virtual environment.

    On Windows, use the Python launcher so the environment is created
    explicitly with Python 3.11 instead of the system default Python.

    On Linux/macOS, use python3.11.
    """

    if os.name == "nt":
        command = [
            "py",
            "-3.11",
            "-m",
            "venv",
            venv_path,
        ]
    else:
        command = [
            "python3.11",
            "-m",
            "venv",
            venv_path,
        ]

    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


def run_tests(
    repo_path: str,
    venv_dir: str = ".depgraph-venv",
) -> TestResult:

    repo_path = os.path.abspath(repo_path)
    venv_path = os.path.join(repo_path, venv_dir)

    # ---------------------------------------------------------
    # STEP 0: Create a fresh Python 3.11 environment
    # ---------------------------------------------------------
    if os.path.exists(venv_path):
        shutil.rmtree(venv_path)

    try:
        create_test_venv(venv_path)

    except subprocess.TimeoutExpired:
        return TestResult(
            passed=False,
            return_code=-1,
            stdout="",
            stderr="Creating the Python 3.11 test environment timed out.",
            stage="timeout",
        )

    except subprocess.CalledProcessError as exc:
        return TestResult(
            passed=False,
            return_code=exc.returncode,
            stdout=exc.stdout or "",
            stderr=(
                (exc.stderr or "")
                + "\nFailed to create the Python 3.11 "
                "test environment."
            ),
            stage="install",
        )

    # ---------------------------------------------------------
    # Locate venv executables
    # ---------------------------------------------------------
    if os.name == "nt":
        pip = os.path.join(
            venv_path,
            "Scripts",
            "pip.exe",
        )

        python = os.path.join(
            venv_path,
            "Scripts",
            "python.exe",
        )

    else:
        pip = os.path.join(
            venv_path,
            "bin",
            "pip",
        )

        python = os.path.join(
            venv_path,
            "bin",
            "python",
        )

    # ---------------------------------------------------------
    # STEP 1: Install dependencies
    # ---------------------------------------------------------
    try:
        install = subprocess.run(
            [
                pip,
                "install",
                "-q",
                "-r",
                "requirements.txt",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=180,
        )

    except subprocess.TimeoutExpired as exc:
        return TestResult(
            passed=False,
            return_code=-1,
            stdout=exc.stdout or "",
            stderr=(
                (exc.stderr or "")
                + "\nDependency installation timed out."
            ),
            stage="timeout",
        )

    if install.returncode != 0:
        return TestResult(
            passed=False,
            return_code=install.returncode,
            stdout=install.stdout,
            stderr=install.stderr,
            stage="install",
        )

    # ---------------------------------------------------------
    # STEP 2: Run tests
    # ---------------------------------------------------------
    try:
        test = subprocess.run(
            [
                python,
                "-m",
                "pytest",
                "tests/",
                "-v",
            ],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

    except subprocess.TimeoutExpired as exc:
        return TestResult(
            passed=False,
            return_code=-1,
            stdout=exc.stdout or "",
            stderr=(
                (exc.stderr or "")
                + "\nTest execution timed out."
            ),
            stage="timeout",
        )

    return TestResult(
        passed=(test.returncode == 0),
        return_code=test.returncode,
        stdout=test.stdout,
        stderr=test.stderr,
        stage="test",
    )


if __name__ == "__main__":
    import sys

    result = run_tests(
        sys.argv[1]
        if len(sys.argv) > 1
        else "../../target-repo"
    )

    print(f"PASSED: {result.passed}")
    print(f"STAGE: {result.stage}")
    print(result.stdout[-1500:])
    print(result.stderr[-1500:])