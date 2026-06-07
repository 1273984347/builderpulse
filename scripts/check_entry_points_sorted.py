#!/usr/bin/env python3
"""Verify all [project.entry-points."..."] groups are alphabetically sorted.
Compatible with Python 3.9+ (uses tomli as fallback for pre-3.11)."""
import sys

try:
    import tomllib
except ImportError:
    import tomli as tomllib


def main() -> int:
    with open("pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    eps = data.get("project", {}).get("entry-points", {})
    failed = []
    for group, entries in eps.items():
        names = list(entries.keys())
        if names != sorted(names):
            failed.append(f"  {group}: {names} (expected {sorted(names)})")
    if failed:
        print("Entry points NOT alphabetically sorted:")
        print("\n".join(failed))
        return 1
    print("OK: all entry_points alphabetically sorted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
