#!/usr/bin/env python3
"""Update Feeds - cron-driven aggregator for BuilderPulse content sources.

Used by .github/workflows/generate-feed.yml (and any local cron / Task Scheduler
setup) to fetch recent items from all configured sources and emit a JSON
manifest.

Configuration is read from BUILDERPULSE_CONFIG_PATH (12-factor app env var,
matching ConfigManager.get_config_path()). When unset, falls back to
Config.from_defaults() (empty feeds, fetches nothing - cron still passes).

Privacy: This script does NOT read any user-specific secrets. Twitter requires
X_BEARER_TOKEN to be set in the environment; without it TwitterSource.fetch()
returns an empty list and the cron run still succeeds.

Origin (Session 35): Previously inlined as `python -c "..."` in the workflow
file, which broke when GitHub Actions runner image was bumped (YAML leading
whitespace was interpreted as Python indentation, causing IndentationError).
Extracting to a script file makes the code immune to that class of YAML /
Python string-literal edge cases.
"""
from __future__ import annotations

import json
import os
import sys


def main() -> int:
    # Lazy import - only require builderpulse when actually run.
    from builderpulse.core.config import Config
    from builderpulse.core.source_aggregator import fetch_all_sources

    # 1) Resolve config (12-factor app env var, matches ConfigManager 范式).
    config_path = os.environ.get("BUILDERPULSE_CONFIG_PATH")
    if config_path and os.path.exists(config_path):
        cfg = Config.from_file(config_path)
        config_source = config_path
    else:
        cfg = Config.from_defaults()
        config_source = "<defaults (no BUILDERPULSE_CONFIG_PATH set)>"

    # 2) Build dict-shaped config (source_aggregator.fetch_all_sources expects dict).
    config_dict = cfg.to_dict(mask_secrets=True)

    # 3) Fetch from all enabled sources.
    items, errors = fetch_all_sources(config_dict, days=1)

    if errors:
        for err in errors:
            print(f"[WARN] {err}", file=sys.stderr)

    # 4) Emit JSON manifest.
    manifest = [
        {"title": getattr(item, "title", ""), "url": getattr(item, "url", "")}
        for item in items[:50]
    ]
    print(json.dumps(manifest, indent=2, ensure_ascii=False))

    print(
        f"[INFO] config={config_source}, items={len(items)}, errors={len(errors)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
