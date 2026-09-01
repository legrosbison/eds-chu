#!/usr/bin/env python3
"""Create a local .env file and a strong pseudonymization key if needed."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / ".env.example"
TARGET = ROOT / ".env"
PLACEHOLDER = "replace-with-a-long-random-secret"


def main() -> None:
    if TARGET.exists():
        content = TARGET.read_text(encoding="utf-8")
    elif EXAMPLE.exists():
        content = EXAMPLE.read_text(encoding="utf-8")
    else:
        content = ""

    generated = secrets.token_urlsafe(48)
    lines = content.splitlines()
    found = False
    output: list[str] = []
    for line in lines:
        if line.startswith("PSEUDONYMIZATION_KEY="):
            found = True
            current = line.split("=", 1)[1]
            if len(current) < 32 or current == PLACEHOLDER:
                line = f"PSEUDONYMIZATION_KEY={generated}"
        output.append(line)
    if not found:
        output.append(f"PSEUDONYMIZATION_KEY={generated}")

    TARGET.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.chmod(TARGET, 0o600)
    print(f"Ready: {TARGET} (permissions 0600)")


if __name__ == "__main__":
    main()
