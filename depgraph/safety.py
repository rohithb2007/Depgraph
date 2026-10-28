"""Heuristic secret guards. Findings never include the matched secret value."""

import os
import re
from pathlib import Path

PRIVATE_DIRS = {".aws", ".azure", ".ssh", ".gnupg", ".kube", ".gcloud"}
PRIVATE_NAMES = {
    "credentials.json",
    "service-account.json",
    "service_account.json",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    ".netrc",
    ".pypirc",
    ".npmrc",
}
PRIVATE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}
SECRET_PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "GitHub token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{25,})"),
    "API secret key": re.compile(r"sk-[A-Za-z0-9_-]{25,}"),
    "AWS access key": re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "Credential URL": re.compile(
        r"(?i)(?:https?|postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s/:]+:[^\s/@]+@"
    ),
}
ASSIGNMENT = re.compile(
    r"""(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*["']([^"'\r\n]{12,})["']"""
)
PLACEHOLDERS = {
    "your-gemini-api-key-here",
    "your-api-key-here",
    "your-password-here",
    "your-token-here",
    "replace-with-your-key",
}


def private_path(path, *, allow_template=False):
    path = Path(path)
    parts = {p.lower() for p in path.parts}
    name = path.name.lower()
    template = name in {".env.example", ".env.sample", ".env.template"}
    return (
        bool(parts & PRIVATE_DIRS)
        or name in PRIVATE_NAMES
        or path.suffix.lower() in PRIVATE_SUFFIXES
        or (
            (name == ".env" or name.startswith(".env.") or name.endswith(".env"))
            and not (allow_template and template)
        )
    )


def secret_findings(text):
    findings = []
    for label, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append((label, text.count("\n", 0, match.start()) + 1))
    for match in ASSIGNMENT.finditer(text):
        if match[1] not in PLACEHOLDERS:
            findings.append(("Assigned credential", text.count("\n", 0, match.start()) + 1))
    return findings


def redact(text):
    for pattern in SECRET_PATTERNS.values():
        text = pattern.sub("[REDACTED]", text)
    text = ASSIGNMENT.sub(lambda m: m[0] if m[1] in PLACEHOLDERS else m[0].replace(m[1], "[REDACTED]"), text)
    # Also mask exact credential values inherited by the parent process.
    for name, value in os.environ.items():
        if len(value) >= 8 and any(
            part in name.upper() for part in ("TOKEN", "SECRET", "PASSWORD", "API_KEY")
        ):
            text = text.replace(value, "[REDACTED]")
    return text


def execution_environment():
    allowed = {
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATH",
        "PATHEXT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "NUMBER_OF_PROCESSORS",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(
        PYTHONNOUSERSITE="1",
        PYTHONDONTWRITEBYTECODE="1",
        PIP_CONFIG_FILE=os.devnull,
        PIP_NO_INPUT="1",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
    )
    return env
