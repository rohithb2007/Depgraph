"""
DepGraph Gemini diagnosis tool.

Takes a failing test's output plus the relevant source file,
asks Gemini to:
1. explain the compatibility problem
2. propose the smallest possible source-code patch

The Gemini response is validated before it becomes a Diagnosis object.

Gemini is the reasoning engine.
DepGraph's deterministic code is responsible for applying and
verifying the proposed change.

The API key is loaded from the environment/.env and is never
hardcoded here.
"""

import json
import os
import re
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


GEMINI_MODEL = "gemini-3.5-flash"

# Maximum time to wait for one Gemini HTTP request.
# This prevents the entire agent from hanging indefinitely.
GEMINI_TIMEOUT_SECONDS = 60


@dataclass
class Diagnosis:
    root_cause: str
    file_to_patch: str
    find: str
    replace: str
    confidence: str
    source: str = "unknown"
    model: str = ""


DIAGNOSIS_PROMPT = """You are DepGraph, an autonomous dependency-upgrade agent.

A dependency was just upgraded and the application's test suite now fails.

Your job is to diagnose the compatibility problem and propose the
SMALLEST possible source-code patch that fixes it without downgrading
the dependency.

Package upgraded:
{package} {old_version} -> {new_version}

Failing test output:
{test_output}

Source of the file most likely responsible:
{file_path}

Source code:
{file_source}

IMPORTANT RULES:

1. Diagnose only the application/test failure shown above.
2. Do not propose changing dependency versions.
3. Do not invent files or source code that were not provided.
4. The patch must be as small as possible.
5. The "find" string must match the provided source EXACTLY.
6. The replacement must be valid source code.
7. If you cannot confidently propose a safe patch, return empty
   "find" and "replace" strings and use confidence "low".
8. Return file_to_patch as the path relative to the target repository root.
   Do not return an absolute path.

Respond with ONLY a JSON object.

Use exactly this shape:

{{
  "root_cause": "<one or two sentences>",
  "file_to_patch": "<filename>",
  "find": "<exact substring of the current source to replace>",
  "replace": "<replacement substring>",
  "confidence": "high"
}}

The confidence value must be exactly one of:
"high", "medium", "low".
"""


def _call_gemini(prompt: str) -> str:
    """
    Call Gemini with a bounded HTTP timeout.

    Raises an exception if Gemini cannot be reached or the request
    fails. The caller is responsible for handling that failure safely.
    """

    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Configure it through .env or the environment."
        )

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=GEMINI_TIMEOUT_SECONDS * 1000,
        ),
    )

    print(">>> DIAGNOSIS SOURCE: GEMINI")

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    if not response.text:
        raise RuntimeError(
            "Gemini returned an empty response."
        )

    return response.text


def _fallback_heuristic(
    package: str,
    test_output: str,
    file_source: str,
    file_path: str,
) -> Diagnosis:
    """
    Offline stand-in used only when GEMINI_API_KEY is not set.

    This exists so the project remains runnable offline.

    It is NOT the real diagnosis engine.
    """

    print(">>> DIAGNOSIS SOURCE: FALLBACK")

    if (
        "yaml.load() missing" in test_output.replace(
            "load(",
            "load() missing",
        )
        or "Loader" in test_output
    ):
        old = "yaml.load(f)  # <-- breaks on PyYAML >= 6.0"

        if old in file_source:
            return Diagnosis(
                root_cause=(
                    "PyYAML >= 6.0 made the Loader argument to "
                    "yaml.load() required; the old call site omitted it."
                ),
                file_to_patch=file_path,
                find=old,
                replace=(
                    "yaml.load(f, Loader=yaml.SafeLoader) "
                    "# patched by DepGraph"
                ),
                confidence="high",
                source="fallback",
                model="",
            )

    return Diagnosis(
        root_cause=(
            "No offline heuristic matched this failure - "
            "set GEMINI_API_KEY for real diagnosis."
        ),
        file_to_patch=file_path,
        find="",
        replace="",
        confidence="low",
        source="fallback",
        model="",
    )


def _validate_gemini_data(
    data: dict,
    file_path: str,
    file_source: str,
    repo_path: str,
) -> Diagnosis:
    """
    Validate Gemini's JSON before allowing it into the agent loop.

    Gemini proposes.
    DepGraph validates.
    """

    required_fields = {
        "root_cause",
        "file_to_patch",
        "find",
        "replace",
        "confidence",
    }

    missing = required_fields - set(data.keys())

    if missing:
        raise ValueError(
            f"Gemini response missing required fields: "
            f"{sorted(missing)}"
        )

    confidence = data["confidence"]

    if confidence not in {"high", "medium", "low"}:
        raise ValueError(
            f"Invalid confidence value from Gemini: {confidence!r}"
        )

    root_cause = data["root_cause"]
    file_to_patch = data["file_to_patch"]
    find = data["find"]
    replace = data["replace"]

    if not isinstance(root_cause, str):
        raise ValueError("Gemini root_cause must be a string.")

    if not isinstance(file_to_patch, str):
        raise ValueError("Gemini file_to_patch must be a string.")

    if not isinstance(find, str):
        raise ValueError("Gemini find must be a string.")

    if not isinstance(replace, str):
        raise ValueError("Gemini replace must be a string.")

    # Gemini must only patch the source file we actually supplied.
    if os.path.isabs(file_to_patch):
        raise ValueError("Gemini proposed an absolute path, which is not allowed.")

    repo_abs = os.path.abspath(repo_path)
    resolved_proposed = os.path.normpath(os.path.join(repo_abs, file_to_patch))
    resolved_expected = os.path.normpath(os.path.abspath(file_path))

    if os.path.commonpath([repo_abs, resolved_proposed]) != repo_abs:
        raise ValueError("Gemini proposed a path outside the target repository.")

    if resolved_proposed != resolved_expected:
        raise ValueError(
            "Gemini proposed a different file than the inspected file."
        )

    # If no patch is proposed, allow the diagnosis to continue.
    if not find:
        return Diagnosis(
            root_cause=root_cause,
            file_to_patch=file_path,
            find="",
            replace="",
            confidence=confidence,
            source="gemini",
            model=GEMINI_MODEL,
        )

    # A proposed patch MUST have a replacement.
    if not replace:
        raise ValueError(
            "Gemini proposed a find string but an empty replacement."
        )

    # Most important deterministic safety check:
    # the exact text Gemini wants to replace must exist.
    if find not in file_source:
        raise ValueError(
            "Gemini patch rejected: the proposed 'find' text "
            "does not exist exactly in the current source."
        )

    # Avoid a no-op patch.
    if find == replace:
        raise ValueError(
            "Gemini patch rejected: replacement is identical "
            "to the original source."
        )

    return Diagnosis(
        root_cause=root_cause,
        file_to_patch=file_path,
        find=find,
        replace=replace,
        confidence=confidence,
        source="gemini",
        model=GEMINI_MODEL,
    )


def diagnose_and_patch(
    package: str,
    old_version: str,
    new_version: str,
    test_output: str,
    file_path: str,
    file_source: str,
    repo_path: str,
) -> Diagnosis:

    # ---------------------------------------------------------
    # Offline fallback
    # ---------------------------------------------------------
    if not os.environ.get("GEMINI_API_KEY"):
        return _fallback_heuristic(
            package,
            test_output,
            file_source,
            file_path,
        )

    # ---------------------------------------------------------
    # Build Gemini prompt
    # ---------------------------------------------------------
    prompt = DIAGNOSIS_PROMPT.format(
        package=package,
        old_version=old_version,
        new_version=new_version,
        test_output=test_output[-5000:],
        file_path=file_path,
        file_source=file_source,
    )

    # ---------------------------------------------------------
    # Gemini request
    # ---------------------------------------------------------
    try:
        raw = _call_gemini(prompt)

    except Exception as exc:
        # Do not allow a Gemini/network failure to crash the
        # entire DepGraph process.
        print(
            f"  Gemini diagnosis failed: "
            f"{type(exc).__name__}: {exc}"
        )

        return Diagnosis(
            root_cause=(
                "Gemini diagnosis failed before a safe patch "
                "could be produced."
            ),
            file_to_patch=file_path,
            find="",
            replace="",
            confidence="low",
            source="gemini",
            model=GEMINI_MODEL,
        )

    # ---------------------------------------------------------
    # Clean markdown fences if Gemini accidentally adds them
    # ---------------------------------------------------------
    raw = re.sub(
        r"^```(?:json)?\s*",
        "",
        raw.strip(),
        flags=re.IGNORECASE,
    )

    raw = re.sub(
        r"\s*```$",
        "",
        raw.strip(),
    ).strip()

    # ---------------------------------------------------------
    # Parse JSON
    # ---------------------------------------------------------
    try:
        data = json.loads(raw)

    except json.JSONDecodeError as exc:
        print(
            f"  Gemini returned invalid JSON: {exc}"
        )

        return Diagnosis(
            root_cause=(
                "Gemini returned a response that could not be "
                "parsed as valid JSON."
            ),
            file_to_patch=file_path,
            find="",
            replace="",
            confidence="low",
            source="gemini",
            model=GEMINI_MODEL,
        )

    # ---------------------------------------------------------
    # Validate proposed diagnosis and patch
    # ---------------------------------------------------------
    try:
        return _validate_gemini_data(
            data,
            file_path,
            file_source,
            repo_path,
        )

    except ValueError as exc:
        print(
            f"  Gemini diagnosis rejected by safety validation: "
            f"{exc}"
        )

        return Diagnosis(
            root_cause=(
                f"Gemini produced a response that failed "
                f"DepGraph safety validation: {exc}"
            ),
            file_to_patch=file_path,
            find="",
            replace="",
            confidence="low",
            source="gemini",
            model=GEMINI_MODEL,
        )