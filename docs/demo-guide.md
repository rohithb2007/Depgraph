# A five-minute technical demo

## 1. Start with the problem

“Updating a version number is easy. Establishing that the resulting application still works is the hard part. DepGraph makes that evidence visible and keeps the original source unchanged until review.”

Start the workbench with `python -m depgraph serve`. Click **Run offline demo**. Explain immediately that the package APIs are local fixtures, the repair is a deterministic rule, and the subprocess tests are real.

## 2. Explain the three outcomes

Inspect responsekit. Its original API has a `legacy_float` alias. Version 2 removes it, so the contract test raises an attribute error. The fixture repair replaces that call with built-in `float`, and another subprocess validates the result.

Inspect formatkit. The version changes without breaking the tested contract, so it is accepted without a repair.

Inspect guardkit. Version 2 violates the authorization contract. There is no safe repair rule for it. The candidate is restored while the earlier accepted upgrades remain in the disposable workspace.

## 3. Show the evidence

Open **Execution evidence**. Describe baseline testing, each candidate transition, command exit codes, and recorded output. Hash-linked events make accidental artifact edits detectable; do not call them signed or tamper-proof.

Open **Review patch**. Show the requirements diff: two upgraded packages and guardkit still pinned. Show the one application edit and the absence of test edits. Explain why demo apply is disabled.

Export JSON. For a portable HTML report:

```bash
python -m depgraph report RUN_ID --output execution-report.html
```

## 4. Distinguish the real execution path

Real analysis uses PyPI and OSV, a fresh virtual environment for each validation, pip dependency checks, pytest, and pip freeze. Major upgrades and unavailable security data require explicit policy choices. Optional Gemini repair is enabled through an API key and an explicit model selection. Its live behavior is not demonstrated by the offline fixture.

## 5. Explain one failure mode clearly

“If a developer edits the repository after analysis, apply rejects the stale patch. If a caught write failure occurs midway through apply, original bytes are restored. A hard process kill during a multi-file apply still needs manual recovery; that is a known boundary rather than a claim of filesystem transactionality.”

## Questions worth being ready for

| Question | Engineering answer |
| --- | --- |
| Why test the baseline? | Otherwise existing failures could be misattributed to the upgrade and trigger an incorrect repair. |
| Why not let the model edit the repository? | The engine controls paths, edit scope, validation, and apply. The provider supplies a proposal. |
| What if OSV times out? | Unknown is a separate state; the default policy blocks that candidate. |
| Is a venv a sandbox? | It isolates Python packages. Host permissions remain available; trusted repositories only. |
| Is this a complete dependency graph? | The visual is an AST import-impact map. Resolved package versions are recorded, but transitive graph resolution is not implemented. |
| What makes the demo reproducible? | Fixed local API fixtures, deterministic repair, and actual subprocess assertions. |
| What would you build next? | A hardened container runner, lockfile adapters, transitive auditing, and crash-recoverable apply. |

Suggested resume wording, adjusted to what you can personally explain: “Built a Python dependency maintenance workbench with baseline validation, disposable upgrade workspaces, security gates, constrained compatibility repair, and reviewable execution evidence.” Avoid invented adoption, latency, accuracy, or vulnerability-reduction numbers.
