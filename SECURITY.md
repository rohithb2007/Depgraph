# Security and privacy

DepGraph is a **local tool for trusted repositories**. It must not be exposed as a public web service.
Virtual environments and disposable source copies are not operating-system sandboxes. Target code can
still access resources allowed to the user running it. Do not analyze unknown repositories on your host.

## Credentials and AI

- Keep real credentials outside source control. Environment variants, common key files, provider
  credential directories, and generated run reports are excluded by default.
- AI is disabled unless `DEPGRAPH_ENABLE_AI=1`, `GEMINI_API_KEY`, and `DEPGRAPH_MODEL` are configured.
  Enabling it permits application source and redacted failure logs to be sent to the configured provider.
- Known credential patterns in source block an AI request. Target commands inherit a small allowlist
  of system environment variables; pip user configuration is disabled and installs require PyPI wheels.
- Output redaction and secret scanning are heuristic. They cannot recognize every secret, and do not
  prevent trusted target code from reading the host filesystem or accessing the network.
- Run JSON and HTML reports include source diffs, test output, and local paths. Keep them private unless
  you have reviewed their contents. They are excluded from Git by default.

## Before committing

```bash
python scripts/scan_secrets.py
python scripts/scan_secrets.py --history
git config --local core.hooksPath .githooks
```

For a dependency audit, install `pip-audit==2.10.1` in the project environment and run
`python scripts/audit_dependencies.py`. Install `.[ai]` first to include the optional provider SDK.
The audit records exact installed versions under ignored `.depgraph/audit/` and excludes only the
local DepGraph distribution, which has no published advisory record of its own.

The first command scans staged file contents, not just the working tree. The hook fails closed when the
project environment is unavailable. The history scan examines all locally reachable commits. These
checks print finding locations and types without exposing matched values. GitHub Actions also runs the
history scan and a dependency vulnerability audit. CI checks report problems after publication; the
local hook helps block them before commit. Enable GitHub secret scanning and push protection in the
repository's security settings where available; a repository file cannot enable those account settings.

## Reporting and response

Use GitHub's private vulnerability reporting channel if enabled. Do not publish credentials or sensitive
proofs in public issues. If a credential is ever committed, revoke or rotate it immediately. Removing a
file or rewriting Git history does not invalidate a key and does not erase existing clones or caches.

Commit authorship uses GitHub's noreply address. Rewriting public history can remove an email from the
current branch, but it cannot guarantee that prior public copies have disappeared.

Review `docs/architecture.md` for the limits of patch integrity checks, apply rollback, and host execution.
