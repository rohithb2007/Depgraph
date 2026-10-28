"""Atomic, versioned run records and append-only hash-linked event evidence."""

import hashlib
import json
import os
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path


def now():
    return datetime.now(UTC).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if os.name != "nt" or attempt == 5:
                    raise
                # Windows scanners may briefly hold a file without delete sharing.
                time.sleep(0.02 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def save(self, run):
        with self.lock:
            atomic_json(self.root / f"{run['id']}.json", run)

    def get(self, run_id):
        if len(run_id) != 32 or any(c not in "0123456789abcdef" for c in run_id):
            raise ValueError("Invalid run id")
        with self.lock:
            return json.loads((self.root / f"{run_id}.json").read_text(encoding="utf-8"))

    def list(self):
        with self.lock:
            runs = [json.loads(p.read_text(encoding="utf-8")) for p in self.root.glob("*.json")]
        return sorted(runs, key=lambda r: r["created_at"], reverse=True)

    def event(self, run, stage, message, **data):
        events = run.setdefault("events", [])
        event = {
            "sequence": len(events) + 1,
            "at": now(),
            "stage": stage,
            "message": message,
            "data": data,
            "previous_hash": events[-1]["hash"] if events else "0" * 64,
        }
        event["hash"] = digest(event)
        events.append(event)
        self.save(run)


def verify_events(events):
    previous = "0" * 64
    for sequence, event in enumerate(events, 1):
        body = {k: v for k, v in event.items() if k != "hash"}
        if body.get("sequence") != sequence or body.get("previous_hash") != previous:
            return False
        if digest(body) != event.get("hash"):
            return False
        previous = event["hash"]
    return True
