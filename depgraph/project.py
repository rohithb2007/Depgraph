"""Strict manifest parsing and source-level dependency impact analysis."""

import ast
import hashlib
import os
import re
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from .safety import PRIVATE_DIRS

IGNORED = {
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".depgraph",
    ".depgraph-venv",
    "build",
    "dist",
    ".ruff_cache",
}
IGNORED.update(PRIVATE_DIRS)
ALIASES = {
    "yaml": "pyyaml",
    "PIL": "pillow",
    "sklearn": "scikit-learn",
    "cv2": "opencv-python",
    "dotenv": "python-dotenv",
    "bs4": "beautifulsoup4",
}


def source_files(root: Path):
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED and not Path(parent, d).is_symlink())
        for name in sorted(files):
            path = Path(parent, name)
            if not path.is_symlink():
                yield path


def inventory(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files(root)
    }


def manifest(root: Path) -> list[dict]:
    path = root / "requirements.txt"
    if not path.is_file() or path.is_symlink():
        raise ValueError("A regular requirements.txt with exact package pins is required")
    result, seen = [], set()
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        text = re.split(r"\s+#", line, maxsplit=1)[0].strip()
        if not text or text.startswith("#"):
            continue
        try:
            req = Requirement(text)
        except Exception as exc:
            raise ValueError(f"requirements.txt:{number}: unsupported requirement: {text}") from exc
        specs = list(req.specifier)
        if req.url or len(specs) != 1 or specs[0].operator != "==" or "*" in specs[0].version:
            raise ValueError(f"requirements.txt:{number}: use an exact name==version pin")
        name = canonicalize_name(req.name)
        if name in seen:
            raise ValueError(f"Duplicate requirement: {name}")
        seen.add(name)
        result.append(
            {
                "name": name,
                "version": specs[0].version,
                "line": number,
                "active": req.marker is None or req.marker.evaluate(),
            }
        )
    return result


def graph(root: Path, dependencies: list[dict]) -> dict:
    declared = {d["name"] for d in dependencies}
    nodes, edges, warnings = [], [], []
    for path in source_files(root):
        if path.suffix != ".py":
            continue
        relative = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (SyntaxError, UnicodeError) as exc:
            warnings.append({"file": relative, "message": str(exc)})
            continue
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".")[0])
        nodes.append(relative)
        for module in sorted(imports):
            name = canonicalize_name(ALIASES.get(module, module))
            if name in declared:
                edges.append({"file": relative, "package": name, "import": module})
    return {
        "files": nodes,
        "edges": edges,
        "warnings": warnings,
        "kind": "static import impact graph; not a transitive resolver graph",
    }


def bump(path: Path, package: str, version: str):
    lines = path.read_bytes().decode("utf-8").splitlines(keepends=True)
    for i, line in enumerate(lines):
        text = re.split(r"\s+#", line, maxsplit=1)[0].strip()
        if not text or text.startswith("#"):
            continue
        req = Requirement(text)
        if canonicalize_name(req.name) == package:
            # Replace only the exact version span, preserving extras, markers and comments.
            lines[i] = re.sub(r"(==\s*)[^\s;#]+", lambda m: m[1] + version, line, count=1)
            path.write_bytes("".join(lines).encode("utf-8"))
            return
    raise ValueError(f"Requirement not found: {package}")
