#!/usr/bin/env python3
"""Verify pyproject.toml format (indentation, line breaks). Fallback if
taplo is not installed. NOT a sort check — use check_entry_points_sorted.py."""
import sys

try:
    import tomllib
except ImportError:
    import tomli as tomllib


def main() -> int:
    with open("pyproject.toml", "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")

    issues = []
    # Check: no tabs (TOML allows them but PEP 621 convention is 4-space indent)
    if "\t" in text:
        issues.append("Found tab characters; use 4 spaces for indentation")
    # Check: trailing whitespace
    for i, line in enumerate(text.splitlines(), 1):
        if line.rstrip() != line:
            issues.append(f"Line {i}: trailing whitespace")
            break
    # Check: file ends with newline
    if not text.endswith("\n"):
        issues.append("File does not end with newline")

    if issues:
        print("pyproject.toml format issues:")
        for issue in issues:
            print(f"  {issue}")
        return 1
    print("OK: pyproject.toml format")
    return 0


if __name__ == "__main__":
    sys.exit(main())
