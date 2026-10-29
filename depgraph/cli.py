"""Small CLI; analysis is read-only, applying a patch is a separate command."""

import argparse
import json
import sys
from pathlib import Path

from .demo import create_demo
from .engine import Engine
from .store import Store


def main():
    # Redirected Windows output can use a legacy code page. Escape unsupported
    # characters instead of turning a successful validation into a CLI failure.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="DepGraph dependency maintenance workbench")
    parser.add_argument("--state", default=".depgraph/runs", help="Run artifact directory")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="Validate upgrades without modifying source")
    analyze.add_argument("repo", type=Path)
    analyze.add_argument("--allow-major", action="store_true")
    analyze.add_argument("--allow-unknown-security", action="store_true")
    analyze.add_argument(
        "--trust-repo",
        action="store_true",
        required=True,
        help="Acknowledge that installing dependencies and tests executes code",
    )
    commands.add_parser("demo", help="Run offline compatibility fixture with real tests")
    serve = commands.add_parser("serve", help="Open the local maintenance workbench")
    serve.add_argument("--port", default=8080, type=int)
    serve.add_argument("--repo", type=Path, help="Enable trusted analysis for this repository only")
    serve.add_argument("--trust-repo", action="store_true")
    apply = commands.add_parser("apply", help="Apply a reviewed run; rejects stale source")
    apply.add_argument("run_id")
    show = commands.add_parser("show", help="Print a stored run as JSON")
    show.add_argument("run_id")
    report = commands.add_parser("report", help="Export a portable HTML execution report")
    report.add_argument("run_id")
    report.add_argument("--output", type=Path, default=Path("depgraph-report.html"))
    args = parser.parse_args()
    store = Store(args.state)
    engine = Engine(store)
    try:
        if args.command == "serve":
            from .server import serve

            if args.repo and not args.trust_repo:
                parser.error("--repo requires --trust-repo because target tests execute code")
            serve(store, args.port, args.repo)
            return
        if args.command == "report":
            from .report import render_report

            args.output.write_text(render_report(store.get(args.run_id)), encoding="utf-8")
            print(f"Report: {args.output.resolve()}")
            return
        if args.command == "demo":
            engine, run = create_demo(store)
            run = engine.run(run)
        elif args.command == "analyze":
            run = engine.run(
                engine.create(
                    args.repo, allow_major=args.allow_major, allow_unknown=args.allow_unknown_security
                )
            )
        elif args.command == "apply":
            run = engine.apply(args.run_id)
        else:
            print(json.dumps(store.get(args.run_id), indent=2))
            return
        print(f"\nRun {run['id']} · {run['status']}")
        for candidate in run["candidates"]:
            print(f"  {candidate['name']}: {candidate['from']} → {candidate['to']}  {candidate['outcome']}")
        for change in run["changes"]:
            print(change["diff"])
        print(f"Evidence: {store.root / (run['id'] + '.json')}")
        if run["status"] in {"failed", "baseline_failed"}:
            print(run.get("error", "Baseline failed; inspect the evidence for command output."))
            raise SystemExit(1)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"depgraph: {exc}\n")
