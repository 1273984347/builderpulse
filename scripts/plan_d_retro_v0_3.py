"""
Plan D — Retro automation v0.3 (pgvector MemoryStore) — ⚠️ EXPERIMENTAL

Differences from v0.2:
- Add PgVectorMemoryStore with semantic search (cosine similarity)
- v0.2 JSONMemoryStore stays as default (no extra deps)
- v0.3 selected when DATABASE_URL env var is set
- Real embeddings come from the universal LLM adapter (OpenAI text-embedding-3-small)
- Substring fallback if embedding generation fails (khoj pattern: graceful degradation)

⚠️ EXPERIMENTAL (Tier 3 per cycle 11 first-principles audit):
- Code complete but NEVER tested end-to-end (requires docker daemon + postgres setup)
- Mock tests deleted in cycle 11 cleanup
- Use v0.1 or v0.2 until docker postgres is available

Usage:
    # JSON mode (v0.2 default, no DATABASE_URL) — USE THIS INSTEAD
    $ python scripts/plan_d_retro_v0_3.py save "text"
    $ python scripts/plan_d_retro_v0_3.py pull

    # pgvector mode (with DATABASE_URL=postgresql://user:pass@host/db) — EXPERIMENTAL
    $ export DATABASE_URL=postgresql://khoj:khoj@localhost:5432/khoj
    $ export OPENAI_API_KEY=sk-...   # for embedding generation
    $ python scripts/plan_d_retro_v0_3.py save "text"
    # → embed via OpenAI → store as pgvector

Reference: khoj/database/models/__init__.py:768-799 (Entry.embeddings VectorField)
            khoj/database/adapters/__init__.py:2287-2330 (UserMemoryAdapters)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Protocol

# Reuse v0.2 implementation (which reuses v0.1)
sys.path.insert(0, str(Path(__file__).parent))
from plan_d_retro_v0_2 import (  # noqa: E402
    WEEKLY_CRON_HOUR, WEEKLY_CRON_DOW, _CRON_DOW_MAP,
    cmd_status, cmd_serve, _weekly_job,
)
from plan_d_retro_v0_1 import (  # noqa: E402
    MemoryEntry, MemoryStore, PULL_WINDOW_DAYS, RETRIEVAL_TOP_K,
    cmd_save, cmd_pull, cmd_reflect, cmd_weekly,
    _llm_chat,
)

# ---------- v0.3 PgVectorMemoryStore ----------

class MemoryStoreBackend(Protocol):
    """Protocol for memory store backends. Allows pluggable JSON/pgvector/etc."""
    def add(self, raw: str, source: str = "retro", embedding: Optional[List[float]] = None) -> MemoryEntry: ...
    def pull(self, window_days: int = PULL_WINDOW_DAYS, limit: int = RETRIEVAL_TOP_K) -> List[MemoryEntry]: ...
    def search(self, query: str, limit: int = RETRIEVAL_TOP_K) -> List[MemoryEntry]: ...
    def save(self) -> None: ...


class PgVectorMemoryStore:
    """Postgres + pgvector backed memory store.

    Schema (created on first init):
        CREATE TABLE plan_d_memories (
            id TEXT PRIMARY KEY,
            raw TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            source TEXT NOT NULL,
            embedding VECTOR(1536)  -- OpenAI text-embedding-3-small dimension
        );
        CREATE INDEX ON plan_d_memories USING ivfflat (embedding vector_cosine_ops);

    Usage requires:
    - DATABASE_URL env var (postgres:// connection string)
    - pgvector extension installed in the database
    - asyncpg (or psycopg2) driver
    - openai (for embedding generation via universal adapter)
    """

    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_DIM = 1536

    def __init__(self, database_url: Optional[str] = None, openai_api_key: Optional[str] = None):
        self.database_url = database_url or os.environ.get("DATABASE_URL")
        self.openai_api_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        if not self.database_url:
            raise ValueError(
                "PgVectorMemoryStore requires DATABASE_URL. "
                "Either set it or use MemoryStore (JSON backend) instead."
            )
        # Lazy import: don't fail if psycopg2 not installed
        try:
            import psycopg2
            from psycopg2.extras import execute_values
            self._psycopg2 = psycopg2
            self._execute_values = execute_values
        except ImportError as e:
            raise ImportError(
                f"psycopg2 not installed: {e}. "
                "Install with: pip install psycopg2-binary pgvector"
            )
        self._ensure_schema()

    def _conn(self):
        return self._psycopg2.connect(self.database_url)

    def _ensure_schema(self):
        """Create table + index if not exists."""
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS plan_d_memories (
                        id TEXT PRIMARY KEY,
                        raw TEXT NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL,
                        source TEXT NOT NULL,
                        embedding VECTOR({self.EMBEDDING_DIM})
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS plan_d_memories_embedding_idx
                    ON plan_d_memories USING ivfflat (embedding vector_cosine_ops)
                """)
            conn.commit()

    async def _embed(self, text: str) -> List[float]:
        """Generate embedding via OpenAI text-embedding-3-small.

        Uses builderpulse.llm.universal_adapter for the OpenAI client.
        Returns empty list if generation fails (graceful degradation).
        """
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.openai_api_key)
            resp = await client.embeddings.create(model=self.EMBEDDING_MODEL, input=text)
            return resp.data[0].embedding
        except Exception as e:
            print(f"[warn] embedding generation failed: {e}")
            return []

    def add(self, raw: str, source: str = "retro", embedding: Optional[List[float]] = None) -> MemoryEntry:
        """Add memory. If embedding not provided, generate it (sync wrapper for async embed)."""
        if embedding is None:
            embedding = asyncio.run(self._embed(raw)) if self.openai_api_key else []
        entry = MemoryEntry(
            id=f"mem_{int(datetime.now().timestamp() * 1000)}",
            raw=raw,
            created_at=datetime.now(timezone.utc).isoformat(),
            embedding=embedding,
            source=source,
        )
        with self._conn() as conn:
            with conn.cursor() as cur:
                # pgvector expects string format '[1.0,2.0,...]'
                emb_str = f"[{','.join(str(x) for x in embedding)}]" if embedding else None
                cur.execute(
                    "INSERT INTO plan_d_memories (id, raw, created_at, source, embedding) VALUES (%s, %s, %s, %s, %s)",
                    (entry.id, entry.raw, entry.created_at, entry.source, emb_str),
                )
            conn.commit()
        return entry

    def pull(self, window_days: int = PULL_WINDOW_DAYS, limit: int = RETRIEVAL_TOP_K) -> List[MemoryEntry]:
        """Pull recent memories within window (khoj pull_memories pattern)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, raw, created_at, source, embedding::text FROM plan_d_memories "
                    "WHERE created_at >= %s ORDER BY created_at DESC LIMIT %s",
                    (cutoff, limit),
                )
                rows = cur.fetchall()
        return [
            MemoryEntry(
                id=row[0], raw=row[1], created_at=row[2].isoformat(),
                source=row[3], embedding=_parse_pgvector(row[4]),
            )
            for row in rows
        ]

    def search(self, query: str, limit: int = RETRIEVAL_TOP_K) -> List[MemoryEntry]:
        """Semantic search via cosine similarity (khoj search_memories pattern)."""
        query_embedding = asyncio.run(self._embed(query))
        if not query_embedding:
            return self.pull(limit=limit)  # graceful fallback to recent
        q_emb_str = f"[{','.join(str(x) for x in query_embedding)}]"
        with self._conn() as conn:
            with conn.cursor() as cur:
                # pgvector <=> is cosine distance; ORDER BY distance ASC = most similar first
                cur.execute(
                    "SELECT id, raw, created_at, source, embedding::text FROM plan_d_memories "
                    "ORDER BY embedding <=> %s::vector LIMIT %s",
                    (q_emb_str, limit),
                )
                rows = cur.fetchall()
        return [
            MemoryEntry(
                id=row[0], raw=row[1], created_at=row[2].isoformat(),
                source=row[3], embedding=_parse_pgvector(row[4]),
            )
            for row in rows
        ]

    def save(self) -> None:
        """No-op for pgvector (writes are immediate)."""
        pass  # khoj also has no save() for pgvector backend


def _parse_pgvector(emb_str: str) -> List[float]:
    """Parse pgvector string format '[1.0,2.0,...]' to list of floats."""
    if not emb_str:
        return []
    s = emb_str.strip("[]")
    return [float(x) for x in s.split(",")] if s else []


# ---------- v0.3 backend selector ----------

def select_backend() -> MemoryStoreBackend:
    """Pick backend based on env. DATABASE_URL → pgvector, else JSON.

    Used by v0.3 commands to transparently choose backend.
    v0.1/v0.2 commands always use JSON (no change).
    """
    if os.environ.get("DATABASE_URL"):
        try:
            return PgVectorMemoryStore()
        except (ImportError, ValueError) as e:
            print(f"[warn] pgvector unavailable ({e}); falling back to JSON")
    return MemoryStore()


# ---------- v0.3 commands (override v0.2 to use backend selector) ----------

async def cmd_v3_save(text: str):
    """Save using selected backend."""
    store = select_backend()
    entry = store.add(raw=text)
    backend_name = type(store).__name__
    print(f"✓ Saved memory ({backend_name}): {entry.id}")
    print(f"  raw: {text[:120]}{'...' if len(text) > 120 else ''}")


async def cmd_v3_pull():
    """Pull using selected backend."""
    store = select_backend()
    recent = store.pull()
    if not recent:
        print("(no memories in window)")
        return
    backend_name = type(store).__name__
    print(f"=== {len(recent)} recent memories ({backend_name}, last {PULL_WINDOW_DAYS} days) ===")
    for e in recent:
        date = e.created_at[:10]
        print(f"  [{date}] {e.raw[:100]}{'...' if len(e.raw) > 100 else ''}")


async def cmd_v3_search(query: str):
    """Semantic search using selected backend."""
    store = select_backend()
    if not isinstance(store, PgVectorMemoryStore):
        print("(semantic search requires DATABASE_URL/pgvector; falling back to recent pull)")
        await cmd_v3_pull()
        return
    results = store.search(query)
    if not results:
        print("(no results)")
        return
    backend_name = type(store).__name__
    print(f"=== {len(results)} semantic matches for '{query}' ({backend_name}) ===")
    for e in results:
        date = e.created_at[:10]
        print(f"  [{date}] {e.raw[:100]}{'...' if len(e.raw) > 100 else ''}")


# ---------- CLI entry (v0.3 new + v0.1/v0.2 backward compat) ----------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    # v0.3 new
    if cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: plan_d_retro_v0_3.py search 'query text'")
            sys.exit(1)
        asyncio.run(cmd_v3_search(sys.argv[2]))
    # v0.1/v0.2 commands (unchanged interface, v0.3 uses select_backend)
    elif cmd == "save":
        if len(sys.argv) < 3:
            print("Usage: plan_d_retro_v0_3.py save 'memory text'")
            sys.exit(1)
        asyncio.run(cmd_v3_save(sys.argv[2]))
    elif cmd == "pull":
        asyncio.run(cmd_v3_pull())
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
