"""
attempt_upgrade tool.

Rewrites one line of requirements.txt to bump a package to a target
version. Deliberately dumb/deterministic - all the judgment (which
version to try, whether to retry) belongs to the agent's reasoning step,
not here.
"""

import re


def bump_dependency(requirements_path: str, package_name: str, new_version: str) -> None:
    with open(requirements_path, "r") as f:
        lines = f.readlines()

    pattern = re.compile(rf"^{re.escape(package_name)}==", re.IGNORECASE)
    new_lines = []
    found = False
    for line in lines:
        if pattern.match(line.strip()):
            new_lines.append(f"{package_name}=={new_version}\n")
            found = True
        else:
            new_lines.append(line)

    if not found:
        raise ValueError(f"{package_name} not found in {requirements_path}")

    with open(requirements_path, "w") as f:
        f.writelines(new_lines)


if __name__ == "__main__":
    import sys
    bump_dependency(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"Bumped {sys.argv[2]} to {sys.argv[3]} in {sys.argv[1]}")
