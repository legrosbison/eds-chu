#!/usr/bin/env python3
"""Create a local .env file and a strong pseudonymization key if needed."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"
SECRET_PLACEHOLDERS = {
    "PSEUDONYMIZATION_KEY": "replace-with-a-long-random-secret",
    "METABASE_ADMIN_PASSWORD": "replace-with-a-strong-local-password",
    "METABASE_PILOTAGE_PASSWORD": "replace-with-a-strong-local-password",
    "METABASE_RECHERCHE_PASSWORD": "replace-with-a-strong-local-password",
}


def main() -> None:
    example_content = EXAMPLE.read_text(encoding="utf-8") if EXAMPLE.exists() else ""
    if TARGET.exists():
        content = TARGET.read_text(encoding="utf-8")
        existing_names = {
            line.split("=", 1)[0]
            for line in content.splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        }
        missing_lines = [
            line
            for line in example_content.splitlines()
            if "=" in line
            and not line.lstrip().startswith("#")
            and line.split("=", 1)[0] not in existing_names
        ]
        if missing_lines:
            content = content.rstrip() + "\n" + "\n".join(missing_lines) + "\n"
    else:
        content = example_content

    lines = content.splitlines()
    output: list[str] = []
    for line in lines:
        name, separator, current = line.partition("=")
        if separator and name in SECRET_PLACEHOLDERS:
            if len(current) < 16 or current == SECRET_PLACEHOLDERS[name]:
                line = f"{name}={secrets.token_urlsafe(24)}"
        output.append(line)

    present_names = {line.split("=", 1)[0] for line in output if "=" in line}
    for name in SECRET_PLACEHOLDERS:
        if name not in present_names:
            output.append(f"{name}={secrets.token_urlsafe(24)}")

    TARGET.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.chmod(TARGET, 0o600)
    print(f"Ready: {TARGET} (permissions 0600)")


if __name__ == "__main__":
    main()
