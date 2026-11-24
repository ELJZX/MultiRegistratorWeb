#!/usr/bin/env python
"""Verify that all release version markers match the version being released."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "usage: python scripts/check_version.py X.Y.Z|--current",
            file=sys.stderr,
        )
        return 2

    raw = sys.argv[1].strip()
    if raw == "--current":
        settings = read("multiregistrator_web/settings.py")
        match = re.search(
            r'APP_VERSION = os\.environ\.get\("APP_VERSION", "(?P<version>[^"]+)"\)',
            settings,
        )
        if not match:
            print("cannot read APP_VERSION from settings.py", file=sys.stderr)
            return 2
        version = match.group("version")
    else:
        version = raw[1:] if raw.startswith("v") else raw

    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        print(f"invalid version: {version!r}", file=sys.stderr)
        return 2

    errors: list[str] = []

    def check(path: str, pattern: str, label: str) -> None:
        match = re.search(pattern, read(path), re.MULTILINE)
        if not match:
            errors.append(f"{path}: {label} not found")
        elif match.group("version") != version:
            errors.append(
                f"{path}: {label} is {match.group('version')}, expected {version}"
            )

    check(
        "multiregistrator_web/settings.py",
        r'APP_VERSION = os\.environ\.get\("APP_VERSION", "(?P<version>[^"]+)"\)',
        "APP_VERSION default",
    )
    check("Dockerfile", r"^ARG APP_VERSION=(?P<version>\S+)$", "ARG APP_VERSION")
    check(".env.example", r"^APP_VERSION=(?P<version>\S+)$", "APP_VERSION")
    check("package.json", r'"version":\s*"(?P<version>[^"]+)"', "version")
    check("README.md", r"^\*\*Версия: (?P<version>[0-9.]+)\*\*$", "version heading")

    compose = read("docker-compose.yml")
    defaults = re.findall(r"APP_VERSION:-([0-9.]+)", compose)
    if not defaults:
        errors.append("docker-compose.yml: APP_VERSION default not found")
    for found in sorted(set(defaults)):
        if found != version:
            errors.append(
                f"docker-compose.yml: APP_VERSION default is {found}, expected {version}"
            )

    if errors:
        print("Version mismatch:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"Version {version} is consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
