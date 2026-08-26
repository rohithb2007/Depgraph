"""
scan_deps tool.
Parses a requirements.txt and checks each pinned package against PyPI's
JSON API to see if a newer, Python-version-compatible release exists.
Returns a structured list the agent can reason over and decide what to
upgrade.

IMPORTANT: we deliberately do NOT just take PyPI's "latest" version blindly,
and we do NOT check compatibility against whatever Python happens to be
running this script. test_runner.py pins the actual install/test
environment to Python 3.11 (see its docstring) so the demo stays
reproducible regardless of the agent's own Python version. This module
mirrors that same pinned target here, so scan.py's idea of "compatible"
matches what will actually be installed into that venv. If you ever change
the pinned Python version in test_runner.py, update TARGET_PYTHON below to
match.

(In production/deployed form, you'd also cross-reference OSV.dev for known
CVEs so the agent can prioritize security-relevant upgrades over routine
ones - osv.dev isn't reachable from this sandbox's restricted egress, but
Cloud Run has normal internet access, so add that call there.)
"""
import re
import sys
import urllib.request
import json
from dataclasses import dataclass

from packaging.version import Version, InvalidVersion
from packaging.specifiers import SpecifierSet

# Must match the Python version test_runner.py pins the target-repo venv to.
TARGET_PYTHON = Version("3.11")


@dataclass
class DepStatus:
    name: str
    pinned_version: str
    latest_version: str
    is_outdated: bool


REQ_LINE_RE = re.compile(r"^([A-Za-z0-9_.\-]+)==([A-Za-z0-9.\-]+)\s*$")


def parse_requirements(path: str) -> list[tuple[str, str]]:
    deps = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = REQ_LINE_RE.match(line)
            if m:
                deps.append((m.group(1), m.group(2)))
    return deps


def get_latest_compatible_version(package_name: str) -> str:
    """Returns the newest non-yanked release of `package_name` that has at
    least one distribution file compatible with TARGET_PYTHON (the same
    Python version the target repo will actually be installed under).
    Falls back to "unknown" if nothing fits or the lookup fails."""
    url = f"https://pypi.org/pypi/{package_name}/json"
    with urllib.request.urlopen(url, timeout=10) as resp:
        data = json.loads(resp.read())

    releases = data.get("releases", {})

    candidates = []
    for version_str, files in releases.items():
        if not files:
            continue
        try:
            version = Version(version_str)
        except InvalidVersion:
            continue
        if version.is_prerelease:
            continue

        for file_info in files:
            if file_info.get("yanked", False):
                continue
            requires_python = file_info.get("requires_python")
            if not requires_python:
                candidates.append(version)
                break
            try:
                if TARGET_PYTHON in SpecifierSet(requires_python):
                    candidates.append(version)
                    break
            except Exception:
                continue

    if not candidates:
        return "unknown"

    return str(max(candidates))


def scan_deps(requirements_path: str) -> list[DepStatus]:
    results = []
    for name, pinned in parse_requirements(requirements_path):
        try:
            latest = get_latest_compatible_version(name)
        except Exception as e:
            latest = "unknown"
        results.append(
            DepStatus(
                name=name,
                pinned_version=pinned,
                latest_version=latest,
                is_outdated=(latest != "unknown" and latest != pinned),
            )
        )
    return results


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "../target-repo/requirements.txt"
    for dep in scan_deps(path):
        flag = "OUTDATED" if dep.is_outdated else "current"
        print(f"{dep.name:12s} pinned={dep.pinned_version:10s} latest={dep.latest_version:10s} [{flag}]")
