"""
Plan D — Retro automation v0.1 (extracted from khoj-ai/khoj).

Source: khoj/database/models/__init__.py:755-870 (ReflectiveQuestion + UserMemory)
        khoj/database/adapters/__init__.py:2287-2330 (UserMemoryAdapters)
        khoj/routers/api_automation.py (Cron → natural language → query)

The pattern (3 pieces):
1. UserMemory: save meaningful conversation fragments → embed → store → later retrieve
2. ReflectiveQuestion: LLM generates "what should you focus on next?" questions
3. apscheduler: cron triggers the retro flow at scheduled times

v0.1 scope: SINGLE-FILE, JSON-as-storage, async LLM call.
NOT production: no pgvector (uses in-memory + JSON dump), no real apscheduler (cron via CLI).

Usage:
    $ python scripts/plan_d_retro_v0_1.py save "I shipped universal LLM adapter today"
    $ python scripts/plan_d_retro_v0_1.py pull
    $ python scripts/plan_d_retro_v0_1.py reflect
    $ python scripts/plan_d_retro_v0_1.py weekly

Design choice: Use the universal_llm_adapter from builderpulse.llm.
Falls back to local JSON if no LLM_API_KEY env var set.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

# ---------- Shared base (consolidated from this script in session 13) ----------
from plan_d._store import (
    PULL_WINDOW_DAYS,
    RETRIEVAL_TOP_K,
    MemoryEntry,
    MemoryStore,
    MemoryStoreBackend,
)

# ---------- Re-exports (backward compat for `from plan_d_retro_v0_1 import ...`) ----------
__all__ = ["MemoryEntry", "MemoryStore", "MemoryStoreBackend",
           "PULL_WINDOW_DAYS", "RETRIEVAL_TOP_K",
           "MEMORY_FILE", "cmd_save", "cmd_pull", "cmd_reflect", "cmd_weekly"]

# ---------- Config ----------

VAULT_PATH = Path(os.environ.get("BUILDERPULSE_VAULT", "~/.builderpulse")).expanduser()
MEMORY_FILE = VAULT_PATH / "memory" / "retro_memory.json"
# Fallback chain: LLM_API_KEY → OPENAI_API_KEY (common naming convention)
LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL", None)
DEFAULT_MODEL = os.environ.get("LLM_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


# ---------- LLM helper (using universal_adapter) ----------

async def _llm_chat(prompt: str, system: str = "You are a helpful assistant.") -> str:
    """Call LLM via builderpulse.universal_adapter. Returns full text."""
    if not LLM_API_KEY:
        return f"[LLM_API_KEY not set — stub response for: {prompt[:80]}...]"
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
        from builderpulse.llm.universal_adapter import (
            chat, ProviderInfo,
        )
    except ImportError as e:
        return f"[universal_adapter not importable: {e}]"

    chunks: List[str] = []
    async for chunk in chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        provider_info=ProviderInfo(
            name="auto", base_url=LLM_BASE_URL,
            api_key=LLM_API_KEY, model_name=DEFAULT_MODEL,
        ),
    ):
        if chunk.text:
            chunks.append(chunk.text)
    return "".join(chunks)


# ---------- Commands ----------

async def cmd_save(text: str):
    """Save a memory entry."""
    store = MemoryStore()
    entry = store.add(raw=text)
    print(f"✓ Saved memory: {entry.id}")
    print(f"  raw: {text[:120]}{'...' if len(text) > 120 else ''}")


async def cmd_pull():
    """Pull recent memories (khoj pull_memories pattern)."""
    store = MemoryStore()
    recent = store.pull()
    if not recent:
        print("(no memories in window)")
        return
    print(f"=== {len(recent)} recent memories (last {PULL_WINDOW_DAYS} days) ===")
    for e in recent:
        date = e.created_at[:10]  # YYYY-MM-DD
        print(f"  [{date}] {e.raw[:100]}{'...' if len(e.raw) > 100 else ''}")


async def cmd_reflect():
    """Generate reflective questions (khoj ReflectiveQuestion pattern).

    Pulls recent memories → asks LLM to generate 3 questions the user should think about.
    """
    store = MemoryStore()
    recent = store.pull()
    if not recent:
        print("(no memories to reflect on)")
        return
    context = "\n".join(f"- {e.raw}" for e in recent)
    prompt = f"""Based on these recent notes/reflections:

{context}

Generate 3 reflective questions the person should think about for their next session.
Format: one question per line, no numbering."""
    questions = await _llm_chat(
        prompt=prompt,
        system="You generate thoughtful, specific, actionable questions.",
    )
    print("=== Reflective Questions ===")
    for q in questions.strip().split("\n"):
        q = q.strip().lstrip("0123456789.-) ").strip()
        if q:
            print(f"  • {q}")


async def cmd_weekly():
    """Weekly retro flow (khoj apscheduler pattern).

    1. Pull last 7 days of memories
    2. Save a "this week's themes" memory
    3. Generate reflective questions for next week
    """
    print("=== Weekly Retro Flow ===\n")
    store = MemoryStore()
    recent = store.pull(window_days=7, limit=50)
    if not recent:
        print("(no memories this week — skipping retro)")
        return
    print(f"Pulled {len(recent)} memories from last 7 days\n")
    context = "\n".join(f"- {e.raw}" for e in recent)
    summary_prompt = f"""Summarize these notes into 2-3 themes or insights for this week:

{context}

Format: one short theme per line."""
    summary = await _llm_chat(
        prompt=summary_prompt,
        system="You distill notes into clear, concise themes.",
    )
    print("=== This Week's Themes ===")
    for line in summary.strip().split("\n"):
        line = line.strip().lstrip("0123456789.-) ")
        if line:
            print(f"  • {line}")
    # Save the summary as a memory
    store.add(
        raw=f"[Weekly retro {datetime.now(timezone.utc).strftime('%Y-%W')}]\n{summary}",
        source="weekly_retro",
    )
    print(f"\n✓ Saved weekly summary as memory")
    # Then reflect
    print()
    await cmd_reflect()


# ---------- CLI entry ----------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "save":
        if len(sys.argv) < 3:
            print("Usage: plan_d_retro_v0_1.py save 'memory text'")
            sys.exit(1)
        asyncio.run(cmd_save(sys.argv[2]))
    elif cmd == "pull":
        asyncio.run(cmd_pull())
    elif cmd == "reflect":
        asyncio.run(cmd_reflect())
    elif cmd == "weekly":
        asyncio.run(cmd_weekly())
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
