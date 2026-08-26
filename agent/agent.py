"""
DepGraph orchestrator.

This is the act -> observe -> diagnose -> retry -> verify loop that's the
whole point of the project.

The agent distinguishes dependency installation failures from actual test
failures. Gemini is only asked to diagnose application-code failures after
dependencies have successfully installed.

Run:
    python agent.py <path-to-target-repo>
"""

import os
import sys
import json
import time

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "tools")
)

from scan import scan_deps
from upgrade import bump_dependency
from test_runner import run_tests
from diagnose import diagnose_and_patch
from patch import apply_patch
from transaction import Transaction
from risk import assess_risk
from security import assess_security


MAX_PATCH_ATTEMPTS = 3


def find_likely_source_file(repo_path: str) -> str:
    """
    Naive for now: our demo repo has one source file.

    A real version would inspect the repository and locate the
    relevant package usage automatically.
    """
    return os.path.join(repo_path, "app.py")


def run_depgraph(repo_path: str):
    run_log = {
        "repo": repo_path,
        "started_at": time.time(),
        "deps": [],
    }

    requirements_path = os.path.join(
        repo_path,
        "requirements.txt"
    )

    deps = scan_deps(requirements_path)
    
    from graph import build_dependency_graph
    run_log["dependency_graph"] = build_dependency_graph(repo_path, requirements_path)
    
    outdated = [d for d in deps if d.is_outdated]

    print(
        f"Scanned {len(deps)} deps, {len(outdated)} outdated: "
        f"{[d.name for d in outdated]}\n"
    )

    for dep in outdated:
        print(
            f"=== {dep.name}: "
            f"{dep.pinned_version} -> {dep.latest_version} ==="
        )

        # ---------------------------------------------------------
        # SECURITY ASSESSMENT
        # ---------------------------------------------------------
        current_security = assess_security(dep.name, dep.pinned_version)
        candidate_security = assess_security(dep.name, dep.latest_version)

        initial_risk = assess_risk(
            dep.pinned_version, 
            dep.latest_version,
            current_security_status=current_security.status,
            candidate_security_status=candidate_security.status
        )
        print(f"Risk: {initial_risk.score}/100 — {initial_risk.level}")
        if initial_risk.reasons:
            print("Reasons:")
            for r in initial_risk.reasons:
                print(f"  - {r}")
        print()

        dep_log = {
            "name": dep.name,
            "from": dep.pinned_version,
            "to": dep.latest_version,
            "attempts": [],
            "outcome": None,
            "security": {
                "current": {
                    "status": current_security.status,
                    "vulnerabilities": [v.id for v in current_security.vulnerabilities]
                },
                "candidate": {
                    "status": candidate_security.status,
                    "vulnerabilities": [v.id for v in candidate_security.vulnerabilities]
                }
            },
            "risk": {
                "score": initial_risk.score,
                "level": initial_risk.level,
                "reasons": initial_risk.reasons
            }
        }

        # ---------------------------------------------------------
        # TRANSACTION START
        # ---------------------------------------------------------
        tx = Transaction()
        try:
            tx.snapshot(requirements_path)

            # ---------------------------------------------------------
            # STEP 1: Upgrade dependency
            # ---------------------------------------------------------
            bump_dependency(
                requirements_path,
                dep.name,
                dep.latest_version,
            )

            # ---------------------------------------------------------
            # STEP 2: Install dependencies + run tests
            # ---------------------------------------------------------
            result = run_tests(repo_path)

            # ---------------------------------------------------------
            # INSTALLATION FAILURE
            # ---------------------------------------------------------
            if result.stage == "install":
                final_risk = assess_risk(
                    dep.pinned_version, 
                    dep.latest_version, 
                    install_success=False,
                    current_security_status=current_security.status,
                    candidate_security_status=candidate_security.status
                )
                dep_log["risk"] = {
                    "score": final_risk.score,
                    "level": final_risk.level,
                    "reasons": final_risk.reasons
                }

                print(
                    "  dependency installation FAILED before tests ran."
                )
                print(
                    "  Gemini will NOT be asked to patch application code "
                    "for an installation failure."
                )

                dep_log["outcome"] = "dependency_install_failed"
                dep_log["install_error"] = {
                    "return_code": result.return_code,
                    "stdout": result.stdout[-3000:],
                    "stderr": result.stderr[-3000:],
                }

                tx.rollback()

                run_log["deps"].append(dep_log)

                print(
                    f"  could not safely evaluate {dep.name}; "
                    f"rolled back to {dep.pinned_version}.\n"
                )

                continue

            # ---------------------------------------------------------
            # TESTS PASSED
            # ---------------------------------------------------------
            if result.passed:
                final_risk = assess_risk(
                    dep.pinned_version, 
                    dep.latest_version, 
                    install_success=True, 
                    test_success=True,
                    current_security_status=current_security.status,
                    candidate_security_status=candidate_security.status
                )
                dep_log["risk"] = {
                    "score": final_risk.score,
                    "level": final_risk.level,
                    "reasons": final_risk.reasons
                }

                print(
                    "  upgrade succeeded cleanly, no fix needed.\n"
                )

                dep_log["outcome"] = "upgraded_clean"
                tx.commit()
                run_log["deps"].append(dep_log)

                continue

            # ---------------------------------------------------------
            # ACTUAL TEST FAILURE
            # ---------------------------------------------------------
            final_risk = assess_risk(
                dep.pinned_version, 
                dep.latest_version, 
                install_success=True, 
                test_success=False,
                current_security_status=current_security.status,
                candidate_security_status=candidate_security.status
            )
            dep_log["risk"] = {
                "score": final_risk.score,
                "level": final_risk.level,
                "reasons": final_risk.reasons
            }

            print(
                "  tests FAILED after upgrade - diagnosing..."
            )

            source_file = find_likely_source_file(repo_path)
            tx.snapshot(source_file)

            fixed = False

            for attempt in range(1, MAX_PATCH_ATTEMPTS + 1):

                with open(source_file, encoding="utf-8") as f:
                    file_source = f.read()

                diagnosis = diagnose_and_patch(
                    package=dep.name,
                    old_version=dep.pinned_version,
                    new_version=dep.latest_version,
                    test_output=result.stdout + result.stderr,
                    file_path=source_file,
                    file_source=file_source,
                    repo_path=repo_path,
                )

                print(
                    f"  attempt {attempt}: "
                    f"{diagnosis.root_cause} "
                    f"(confidence: {diagnosis.confidence}, "
                    f"source: {diagnosis.source})"
                )

                # -----------------------------------------------------
                # RUN-LOG EVIDENCE
                # -----------------------------------------------------
                attempt_log = {
                    "attempt": attempt,
                    "diagnosis": diagnosis.root_cause,
                    "confidence": diagnosis.confidence,
                    "diagnosis_source": diagnosis.source,
                    "model": diagnosis.model,
                    "patch_find": diagnosis.find,
                    "patch_replace": diagnosis.replace,
                    "patch_applied": False,
                }

                # -----------------------------------------------------
                # NO PATCH PROPOSED / SAFETY REJECTION
                # -----------------------------------------------------
                if not diagnosis.find:

                    if diagnosis.root_cause.startswith(
                        "Gemini produced a response that failed "
                        "DepGraph safety validation:"
                    ):
                        attempt_log["result"] = "diagnosis_rejected"
                    else:
                        attempt_log["result"] = "no_patch_proposed"

                    dep_log["attempts"].append(attempt_log)
                    
                    tx.rollback()

                    break

                # -----------------------------------------------------
                # APPLY PATCH
                # -----------------------------------------------------
                applied = apply_patch(
                    source_file,
                    diagnosis.find,
                    diagnosis.replace,
                )

                attempt_log["patch_applied"] = applied

                if not applied:
                    print(
                        "  patch didn't match source exactly, "
                        "skipping attempt"
                    )

                    attempt_log["result"] = "patch_did_not_match"

                    dep_log["attempts"].append(attempt_log)

                    continue

                # -----------------------------------------------------
                # RETEST AFTER PATCH
                # -----------------------------------------------------
                result = run_tests(repo_path)

                # If installation itself now fails, do not ask Gemini
                # to diagnose it as an application-code failure.
                if result.stage == "install":
                    print(
                        "  patched repository could not install "
                        "dependencies; stopping this repair attempt."
                    )

                    attempt_log["result"] = "dependency_install_failed"

                    attempt_log["install_error"] = {
                        "return_code": result.return_code,
                        "stdout": result.stdout[-3000:],
                        "stderr": result.stderr[-3000:],
                    }

                    dep_log["attempts"].append(attempt_log)

                    break

                attempt_log["result"] = (
                    "tests_passed"
                    if result.passed
                    else "tests_still_failing"
                )

                dep_log["attempts"].append(attempt_log)

                # -----------------------------------------------------
                # SUCCESS
                # -----------------------------------------------------
                if result.passed:
                    print(
                        "  patch applied, tests now PASS.\n"
                    )

                    fixed = True

                    break

                # -----------------------------------------------------
                # RETRY
                # -----------------------------------------------------
                print(
                    "  patch applied but tests still fail, "
                    "retrying..."
                )

            # ---------------------------------------------------------
            # FINAL RESULT
            # ---------------------------------------------------------
            dep_log["outcome"] = (
                "upgraded_and_fixed"
                if fixed
                else "failed_rolled_back"
            )

            if fixed:
                tx.commit()
            else:
                print(
                    f"  giving up or failed to patch, "
                    f"rolling back {dep.name}.\n"
                )
                tx.rollback()

            run_log["deps"].append(dep_log)

        except Exception as e:
            print(f"  Unexpected exception during transaction: {e}")
            tx.rollback()
            raise

    # -------------------------------------------------------------
    # WRITE RUN LOG
    # -------------------------------------------------------------
    run_log["finished_at"] = time.time()

    log_path = os.path.join(
        repo_path,
        "depgraph_run_log.json",
    )

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(run_log, f, indent=2)

    print(f"Run log written to {log_path}")

    return run_log


if __name__ == "__main__":
    target = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "../target-repo"
    )

    run_depgraph(target)