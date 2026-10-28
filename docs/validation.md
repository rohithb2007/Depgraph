# Validation record

Validation performed during the October 26, 2026 local development session on Windows, Python 3.12.14.

## Verified behavior

Final local regression result: **38 tests passed**, with 8 additional subtest cases. Ruff lint, formatting, JavaScript syntax, and Python bytecode compilation checks passed.

- Offline subprocess integration: responsekit repaired, formatkit upgraded, guardkit rolled back; original source hashes unchanged.
- Real registry smoke test: a disposable fixture pinned to `packaging==24.1` upgraded to PyPI-selected `26.3` with major upgrades explicitly enabled. OSV returned clear for the candidate. Baseline and candidate environment creation, pip installation, pip check, pytest, and pip freeze all exited zero. Original fixture retained its initial pin until explicit apply.
- Fault-injected apply restores original bytes on a partial write failure. Stale-source, changed patch, duplicate apply, demo apply, unknown security, known vulnerabilities, baseline failure, and install failure are covered by automated tests.
- HTTP integration tests exercise health/static files, async demo execution, mutation token checks, cross-origin rejection, conflict handling, route restrictions, and unsupported real-target analysis.
- HTML reports escape repository, patch, and command content.
- Browser verification: started the offline demo through the dashboard, inspected successful repair test output, reviewed both source diffs, and confirmed the demo apply button is disabled. A clean restart of the single local server resolved the earlier connection timeout.

The test suite uses real subprocesses for fixture contracts and command timeout behavior; registry unit tests use mocks to keep normal tests offline. The real registry smoke test is separate and its result is a snapshot, not an assertion about future registry state.

## Reproduce checks

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check depgraph tests
python -m ruff format --check depgraph tests
python -m depgraph demo
```

The Windows agent sandbox blocks loopback connections and some process termination operations. The complete HTTP/subprocess suite needs a normal local terminal or an execution environment allowing those operations. An initial Windows file-sharing failure during atomic artifact replacement prompted a bounded retry for transient sharing violations.

## Not claimed as verified

Live Gemini calls were not made; there was no configured key/model. The CI matrix is configured but has not been executed remotely. Docker build/runtime has not been validated in this session. No load, hostile-code containment, or production deployment claim is made.

## October 29, 2026 hardening pass

- 48 local tests passed, including 16 subtest cases. New tests cover staged-secret blocking without
  printing values, credential-file detection, subprocess environment allowlisting, AI opt-in,
  AI rejection of credential-bearing source, and cross-site HTTP/read restrictions.
- Installed core, development, auditing, and optional AI dependencies were checked with pip-audit;
  no known vulnerabilities were reported at the time of the audit. No live AI requests were made.
- GitHub reported secret scanning and push protection already enabled. Dependabot security updates
  and private vulnerability reporting were enabled. The API continued reporting non-provider
  pattern scanning disabled after an enable request, so that optional feature is not claimed enabled.
- The secret checker scans staged content before commit and reachable commit contents in CI. Workflow
  actions are pinned to official immutable revisions; checkout does not retain authentication credentials.
- Credential exclusions, redacted command output, wheel-only target installs, and explicit AI consent
  reduce accidental leaks. They do not turn host execution into a secure sandbox or guarantee safety.
