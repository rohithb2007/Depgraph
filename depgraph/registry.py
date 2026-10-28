"""Bounded registry lookups. Unknown security data never means safe."""

import json
import platform
import urllib.error
import urllib.request

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version


def request_json(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "User-Agent": "DepGraph/0.2"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


class Registry:
    def latest(self, name, current, allow_major=False):
        releases = request_json(f"https://pypi.org/pypi/{name}/json").get("releases", {})
        old, candidates = Version(current), []
        for text, files in releases.items():
            try:
                version = Version(text)
                if version <= old or version.is_prerelease or version.is_devrelease:
                    continue
                if not allow_major and version.major != old.major:
                    continue
                if any(
                    not f.get("yanked")
                    and Version(platform.python_version()) in SpecifierSet(f.get("requires_python") or "")
                    for f in files
                ):
                    candidates.append(version)
            except (InvalidVersion, ValueError):
                continue
        return str(max(candidates)) if candidates else current

    def security(self, name, version):
        try:
            data = request_json(
                "https://api.osv.dev/v1/query",
                {"package": {"name": name, "ecosystem": "PyPI"}, "version": version},
            )
            ids = sorted(v["id"] for v in data.get("vulns", []) if not v.get("withdrawn"))
            return {"status": "vulnerable" if ids else "clear", "ids": ids, "source": "OSV"}
        except (OSError, ValueError, KeyError) as exc:
            return {"status": "unknown", "ids": [], "source": "OSV", "reason": str(exc)}
