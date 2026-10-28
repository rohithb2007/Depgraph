"""Baseline -> isolated upgrade -> repair -> verify -> review -> explicit apply."""

import difflib
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from packaging.version import Version

from .project import bump, graph, inventory, manifest, source_files
from .registry import Registry
from .repair import GeminiRepair, checked_patch
from .runner import VenvRunner
from .safety import private_path
from .store import Store, digest, now, verify_events


class Engine:
    def __init__(self, store: Store, registry=None, runner=None, repair=None):
        self.store = store
        self.registry = registry or Registry()
        self.runner = runner or VenvRunner()
        self.repair = repair or GeminiRepair()

    def create(self, repo, *, allow_major=False, allow_unknown=False, demo=False):
        root = Path(repo).resolve()
        dependencies = manifest(root)
        run = {
            "schema_version": 1,
            "id": uuid.uuid4().hex,
            "repo": str(root),
            "created_at": now(),
            "status": "queued",
            "demo": demo,
            "policy": {"allow_major": allow_major, "allow_unknown_security": allow_unknown},
            "python": os.sys.version.split()[0],
            "dependencies": dependencies,
            "graph": graph(root, dependencies),
            "source_hashes": inventory(root),
            "candidates": [],
            "changes": [],
            "events": [],
        }
        self.store.event(run, "queued", "Repository accepted; source remains untouched")
        return run

    def run(self, run):
        root = Path(run["repo"])
        run["status"] = "running"
        self.store.event(run, "workspace", "Copying source into a disposable workspace")
        try:
            with tempfile.TemporaryDirectory(prefix="depgraph-work-") as folder:
                work = Path(folder) / "repo"
                work.mkdir()
                for source in source_files(root):
                    # Credentials and generated artifacts are not copied into test environments.
                    if private_path(source.relative_to(root)):
                        continue
                    target = work / source.relative_to(root)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                if inventory(root) != run["source_hashes"]:
                    raise ValueError("Source changed while preparing the workspace; start a new run")
                original = {p.relative_to(work).as_posix(): p.read_bytes() for p in source_files(work)}
                self.store.event(
                    run, "baseline", "Installing pinned dependencies and checking baseline tests"
                )
                baseline = self._validate(work)
                run["baseline"] = baseline
                if any((work / p).read_bytes() != data for p, data in original.items()):
                    raise ValueError("Baseline execution modified source inputs")
                if not baseline["passed"]:
                    run["status"] = "baseline_failed"
                    self.store.event(
                        run, "blocked", "Baseline failed; upgrades cannot establish a regression"
                    )
                    return run
                for dep in run["dependencies"]:
                    if dep["active"]:
                        self._candidate(run, work, dep)
                changes = []
                for relative, old in original.items():
                    path = work / relative
                    new = path.read_bytes() if path.exists() else b""
                    if old != new:
                        if relative != "requirements.txt" and (
                            not relative.endswith(".py") or self._is_test(relative)
                        ):
                            raise ValueError(f"Validation modified a protected file: {relative}")
                        before, after = old.decode("utf-8"), new.decode("utf-8")
                        changes.append(
                            {
                                "path": relative,
                                "before": before,
                                "after": after,
                                "diff": "".join(
                                    difflib.unified_diff(
                                        before.splitlines(True),
                                        after.splitlines(True),
                                        fromfile=f"a/{relative}",
                                        tofile=f"b/{relative}",
                                    )
                                ),
                            }
                        )
                # A test that changes tracked inputs must never silently become part of a patch.
                added = set(inventory(work)) - original.keys()
                if any(p.endswith(".py") or p == "requirements.txt" for p in added):
                    raise ValueError("Tests created source files; refusing ambiguous patch")
                run["changes"] = changes
                run["patch_hash"] = digest(changes)
                run["status"] = "ready" if changes else "no_changes"
                self.store.event(
                    run,
                    "complete",
                    "Validated patch ready for review"
                    if changes
                    else "No upgrades passed the configured policy",
                    patch_hash=run["patch_hash"],
                )
        except Exception as exc:
            run["status"] = "failed"
            run["error"] = f"{type(exc).__name__}: {exc}"
            self.store.event(run, "error", run["error"])
        finally:
            run["finished_at"] = now()
            self.store.save(run)
        return run

    @staticmethod
    def _is_test(path):
        p = Path(path)
        return "tests" in p.parts or p.name.startswith("test_") or p.name.endswith("_test.py")

    def _validate(self, work):
        before = inventory(work)
        result = self.runner.validate(work)
        after = inventory(work)
        if any(after.get(path) != sha for path, sha in before.items()):
            raise ValueError("Validation modified source inputs; refusing a self-mutating test run")
        if any(path.endswith(".py") or path == "requirements.txt" for path in after.keys() - before.keys()):
            raise ValueError("Validation created source inputs; refusing ambiguous evidence")
        return result

    def _candidate(self, run, work, dep):
        name, old = dep["name"], dep["version"]
        candidate = {"name": name, "from": old, "to": old, "outcome": "current", "attempts": []}
        run["candidates"].append(candidate)
        self.store.event(run, "scan", f"Finding compatible releases for {name}")
        try:
            target = self.registry.latest(name, old, run["policy"]["allow_major"])
        except Exception as exc:
            candidate.update(outcome="lookup_failed", reason=str(exc))
            self.store.event(run, "registry", f"Release lookup failed for {name}")
            return
        candidate["to"] = target
        if Version(target) <= Version(old):
            return
        if Version(target).major != Version(old).major and not run["policy"]["allow_major"]:
            candidate.update(outcome="policy_blocked", reason="Major upgrades require explicit policy")
            return
        security = self.registry.security(name, target)
        candidate["security"] = security
        impact = sorted({edge["file"] for edge in run["graph"]["edges"] if edge["package"] == name})
        candidate["impact"] = impact
        jump = (
            "major"
            if Version(target).major != Version(old).major
            else ("minor" if Version(target).minor != Version(old).minor else "patch")
        )
        candidate["risk"] = {
            "score": min(
                100,
                {"major": 40, "minor": 20, "patch": 5}[jump]
                + min(20, len(impact) * 2)
                + (10 if security["status"] == "unknown" else 0),
            ),
            "reasons": [
                f"{jump} version change",
                f"{len(impact)} importing files",
                f"candidate security: {security['status']}",
            ],
        }
        if security["status"] == "vulnerable" or (
            security["status"] == "unknown" and not run["policy"]["allow_unknown_security"]
        ):
            candidate["outcome"] = "policy_blocked"
            self.store.event(run, "policy", f"Blocked {name}: candidate security {security['status']}")
            return
        snapshot = {p.relative_to(work).as_posix(): p.read_bytes() for p in source_files(work)}
        accepted = False
        try:
            bump(work / "requirements.txt", name, target)
            self.store.event(run, "validate", f"Testing {name} {old} → {target}")
            result = self._validate(work)
            candidate["validation"] = result
            if not result["passed"] and result["stage"] == "test":
                # Only application files linked to this dependency are considered for repair.
                files = [f for f in impact if not self._is_test(f)]
                for relative in files[:3]:
                    path = work / relative
                    source = path.read_bytes().decode("utf-8")
                    output = "\n".join(c.get("stdout", "") + c.get("stderr", "") for c in result["commands"])
                    try:
                        proposal = self.repair.propose(name, old, target, source, output)
                    except Exception as exc:
                        candidate["attempts"].append(
                            {
                                "file": relative,
                                "rejected": f"Repair provider failed: {type(exc).__name__}",
                            }
                        )
                        continue
                    if not proposal:
                        continue
                    try:
                        updated = checked_patch(source, proposal)
                    except (ValueError, SyntaxError) as exc:
                        candidate["attempts"].append({"file": relative, "rejected": str(exc)})
                        continue
                    path.write_bytes(updated.encode("utf-8"))
                    self.store.event(run, "repair", f"Verifying proposed compatibility repair in {relative}")
                    result = self._validate(work)
                    candidate["attempts"].append(
                        {"file": relative, "proposal": proposal, "validation": result}
                    )
                    if result["passed"]:
                        break
                    path.write_bytes(source.encode("utf-8"))
                    if result["stage"] != "test":
                        break
            accepted = result["passed"]
            # Requirements and tests must be exactly the expected inputs, even if execution passes.
            for relative, content in snapshot.items():
                if self._is_test(relative) and (work / relative).read_bytes() != content:
                    raise ValueError(f"Test modified during execution: {relative}")
            candidate["outcome"] = (
                ("repaired" if candidate["attempts"] else "upgraded") if accepted else "rolled_back"
            )
            candidate["final_validation"] = result
        finally:
            if not accepted:
                for path in list(source_files(work)):
                    if path.relative_to(work).as_posix() not in snapshot:
                        path.unlink()
                for relative, content in snapshot.items():
                    (work / relative).parent.mkdir(parents=True, exist_ok=True)
                    (work / relative).write_bytes(content)
            self.store.event(run, "candidate", f"{name}: {candidate['outcome']}")

    def apply(self, run_id):
        with self.store.lock:
            run = self.store.get(run_id)
            if run["demo"]:
                raise ValueError("Demo patches cannot be applied to a real repository")
            if run["status"] != "ready" or not verify_events(run["events"]):
                raise ValueError("Run is not ready or event integrity verification failed")
            if digest(run["changes"]) != run["patch_hash"]:
                raise ValueError("Patch integrity verification failed")
            root = Path(run["repo"])
            lock = root / ".depgraph" / "apply.lock"
            lock.parent.mkdir(exist_ok=True)
            try:
                handle = lock.open("x")
            except FileExistsError as exc:
                raise ValueError("Another apply is active; inspect .depgraph/apply.lock") from exc
            backups = {}
            try:
                handle.close()
                if inventory(root) != run["source_hashes"]:
                    raise ValueError("Repository changed since analysis; start a new run")
                for change in run["changes"]:
                    relative = change["path"]
                    path = root / relative
                    if path.resolve().parent != root and root not in path.resolve().parents:
                        raise ValueError("Patch path escapes repository")
                    if path.is_symlink() or (
                        relative != "requirements.txt" and (path.suffix != ".py" or self._is_test(relative))
                    ):
                        raise ValueError("Patch targets a protected path")
                    backups[path] = path.read_bytes()
                    if backups[path].decode("utf-8") != change["before"]:
                        raise ValueError("Patch preimage mismatch")
                run["status"] = "applying"
                self.store.event(run, "apply", "Applying reviewed patch with preimage checks")
                for change in run["changes"]:
                    path = root / change["path"]
                    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                        temporary = Path(stream.name)
                        stream.write(change["after"].encode("utf-8"))
                    try:
                        os.chmod(temporary, path.stat().st_mode)
                        os.replace(temporary, path)
                    finally:
                        temporary.unlink(missing_ok=True)
                run["status"] = "applied"
                self.store.event(run, "applied", "Reviewed changes applied successfully")
            except BaseException:
                for path, data in backups.items():
                    path.write_bytes(data)
                if run["status"] in {"applying", "applied"}:
                    run["status"] = "ready"
                    self.store.event(run, "rollback", "Apply failed; original files restored")
                raise
            finally:
                lock.unlink(missing_ok=True)
            return run
