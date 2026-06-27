"""
Plan D — Retro automation v0.2 (apscheduler integration).

Differences from v0.1:
- Add apscheduler-based weekly cron (replaces manual `weekly` CLI call)
- Memory store stays JSON-backed (pgvector deferred to v0.3)
- New `serve` mode: starts background scheduler that calls weekly() every Sunday 9pm
- New `status` command: shows next scheduled run + memory count

Usage:
    # Manual (v0.1 style still works)
    $ python scripts/plan_d_retro_v0_2.py save "memory text"
    $ python scripts/plan_d_retro_v0_2.py pull
    $ python scripts/plan_d_retro_v0_2.py reflect
    $ python scripts/plan_d_retro_v0_2.py weekly

    # v0.2 new commands
    $ python scripts/plan_d_retro_v0_2.py status   # show memory count + next run
    $ python scripts/plan_d_retro_v0_2.py serve    # start apscheduler (blocking)

Scheduling:
- Default: every Sunday at 21:00 local
- Override via env: WEEKLY_CRON_HOUR=21, WEEKLY_CRON_DOW=6  (0=Mon, 6=Sun)

Design choice: keep v0.1 in same file for easy rollback. apscheduler is optional
soft dep — only required for `serve` command.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

# Reuse v0.1 implementation
sys.path.insert(0, str(Path(__file__).parent))
from plan_d_retro_v0_1 import (  # noqa: E402
    MemoryStore, PULL_WINDOW_DAYS, RETRIEVAL_TOP_K,
    cmd_save, cmd_pull, cmd_reflect, cmd_weekly,
    _llm_chat,
)

# ---------- v0.2 Config ----------

WEEKLY_CRON_HOUR = int(os.environ.get("WEEKLY_CRON_HOUR", "21"))  # 9pm
WEEKLY_CRON_DOW = os.environ.get("WEEKLY_CRON_DOW", "sun").lower()  # sun/mon/...
_CRON_DOW_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


# ---------- v0.2 commands ----------

def cmd_status():
    """Show memory count + last activity + next scheduled run."""
    store = MemoryStore()
    count = len(store.entries)
    recent = store.pull(window_days=365, limit=5)
    print("=== Plan D retro — status ===")
    print(f"  Total memories: {count}")
    if recent:
        last = recent[0]
        last_dt = datetime.fromisoformat(last.created_at)
        print(f"  Last memory:   {last_dt.strftime('%Y-%m-%d %H:%M UTC')}  ({last.raw[:50]}...)")
    # Next weekly run
    now = datetime.now()
    days_until = (_CRON_DOW_MAP[WEEKLY_CRON_DOW] - now.weekday()) % 7
    if days_until == 0 and now.hour >= WEEKLY_CRON_HOUR:
        days_until = 7
    next_run = (now + timedelta(days=days_until)).replace(
        hour=WEEKLY_CRON_HOUR, minute=0, second=0, microsecond=0
    )
    print(f"  Next weekly:   {next_run.strftime('%Y-%m-%d %H:%M')} (cron: dow={WEEKLY_CRON_DOW} hour={WEEKLY_CRON_HOUR})")
    # apscheduler installed?
    try:
        import apscheduler  # noqa: F401
        print(f"  apscheduler:   installed ({apscheduler.__version__})")
    except ImportError:
        print("  apscheduler:   NOT installed — install with `pip install apscheduler` for `serve`")


def cmd_serve():
    """Start apscheduler background scheduler that runs weekly() every Sunday 9pm."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as e:
        print(f"❌ apscheduler not installed: {e}")
        print("   Install with: pip install apscheduler")
        sys.exit(1)

    scheduler = BlockingScheduler(timezone="UTC")
    trigger = CronTrigger(
        day_of_week=_CRON_DOW_MAP[WEEKLY_CRON_DOW],
        hour=WEEKLY_CRON_HOUR,
        minute=0,
        timezone="UTC",
    )
    scheduler.add_job(_weekly_job, trigger, id="plan_d_weekly", replace_existing=True)
    print(f"✓ Plan D weekly scheduler started (next: {trigger.get_next_fire_time(None, datetime.now(timezone.utc))})")
    print(f"  Config: dow={WEEKLY_CRON_DOW} hour={WEEKLY_CRON_HOUR} UTC")
    print(f"  Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown(wait=False)
        print("\n✓ Scheduler stopped.")


def _weekly_job():
    """apscheduler callback: run weekly() in event loop."""
    print(f"\n[{datetime.now(timezone.utc).isoformat()}] Plan D weekly trigger fired")
    try:
        asyncio.run(cmd_weekly())
    except Exception as e:
        print(f"❌ weekly() failed: {e}")


# ---------- CLI entry (v0.1 commands + v0.2 new) ----------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "save":
        if len(sys.argv) < 3:
            print("Usage: plan_d_retro_v0_2.py save 'memory text'")
            sys.exit(1)
        asyncio.run(cmd_save(sys.argv[2]))
    elif cmd == "pull":
        asyncio.run(cmd_pull())
    elif cmd == "reflect":
        asyncio.run(cmd_reflect())
    elif cmd == "weekly":
        asyncio.run(cmd_weekly())
    elif cmd == "status":
        cmd_status()
    elif cmd == "serve":
        cmd_serve()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
