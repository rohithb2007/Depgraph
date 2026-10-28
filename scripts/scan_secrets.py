"""Scan the index or reachable history without printing secret values. No network access."""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from depgraph.safety import private_path, secret_findings


def git(*args):
    return subprocess.check_output(["git", *args])


def scan(history=False):
    seen, failures = set(), 0
    revisions = git("rev-list", "--all").decode().splitlines() if history else [None]
    for revision in revisions:
        entries = git("ls-tree", "-rz", revision) if revision else git("ls-files", "--stage", "-z")
        for entry in entries.split(b"\0"):
            if not entry:
                continue
            metadata, raw_path = entry.split(b"\t", 1)
            path = raw_path.decode("utf-8", errors="replace")
            oid = metadata.split()[2 if revision else 1].decode()
            if (oid, path) in seen:
                continue
            seen.add((oid, path))
            if private_path(path, allow_template=True):
                print(f"BLOCKED {path}: credential file must not be committed")
                failures += 1
            data = git("cat-file", "blob", oid)
            # Scan binary data too; keys often occur in serialized files.
            for label, line in secret_findings(data.decode("utf-8", errors="replace")):
                print(f"BLOCKED {path}:{line}: {label} (value withheld)")
                failures += 1
    print(f"Scanned {len(seen)} file versions; {failures} potential leaks.")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    raise SystemExit(scan(args.history))
