"""
plan_d._store — shared base classes for all plan_d retro versions.

Extracted from plan_d_retro_v0_1.py (cycle 11 session 13 consolidation, per
mem-wrap-up v2 schema "工具沉淀与优化 dimension"). The original
MemoryEntry + MemoryStore were defined inline in v0.1 and copy-referenced
by v0.2/v0.3. Now consolidated here for single-source-of-truth.

Versions that use these:
- v0.1 (JSON): imports + re-exports (backward compat for `from plan_d_retro_v0_1 import MemoryStore`)
- v0.2 (apscheduler): imports from v0.1 (unchanged)
- v0.3 (pgvector): imports from v0.1 + adds PgVectorMemoryStore (unchanged)

New code should import directly from `plan_d._store`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Protocol


# ---------- Constants (per khoj UserMemory retention pattern) ----------

# Khoj's UserMemory: 7-day pull window for medium-term memory,
# top-K retrieval for long-term semantic search.
PULL_WINDOW_DAYS = 7
RETRIEVAL_TOP_K = 10


def default_memory_file() -> Path:
    """Resolve default MEMORY_FILE path from env (resolves at call time).

    Reads BUILDERPULSE_VAULT env var (default ~/.builderpulse) → memory/retro_memory.json.
    Called once per MemoryStore() instantiation so changes to env between
    invocations are honored.
    """
    vault = Path(os.environ.get("BUILDERPULSE_VAULT", "~/.builderpulse")).expanduser()
    return vault / "memory" / "retro_memory.json"


# Late import — keep top of file clean
import os  # noqa: E402


# ---------- Data model (mirrors khoj/database/models/__init__.py:855-870) ----------

@dataclass
class MemoryEntry:
    """Mirrors khoj's UserMemory model.

    In khoj, embeddings are pgvector VectorField(dimensions=None).
    v0.1 stores them as a list[float] in JSON. For real use, swap to pgvector.
    """
    id: str
    raw: str
    created_at: str  # ISO 8601
    embedding: List[float] = field(default_factory=list)
    source: str = "retro"  # retro / conversation / automation


# ---------- Backend protocol ----------

class MemoryStoreBackend(Protocol):
    """Protocol for memory store backends. Allows pluggable JSON/pgvector/etc.

    v0.3 uses this protocol to abstract PgVectorMemoryStore vs MemoryStore.
    Defined here so all versions share the same interface contract.
    """
    def add(self, raw: str, source: str = "retro", embedding: Optional[List[float]] = None) -> MemoryEntry: ...
    def pull(self, window_days: int = PULL_WINDOW_DAYS, limit: int = RETRIEVAL_TOP_K) -> List[MemoryEntry]: ...
    def search(self, query: str, limit: int = RETRIEVAL_TOP_K) -> List[MemoryEntry]: ...
    def save(self) -> None: ...


# ---------- JSON implementation (v0.1 base) ----------

class MemoryStore:
    """Trivial in-memory store with JSON file persistence.

    NOT for production. Use pgvector or sqlite-vec for real workloads.
    """

    def __init__(self, path: Path = None):
        self.path = path if path is not None else default_memory_file()
        self.entries: List[MemoryEntry] = []
        if self.path.exists():
            self.entries = [MemoryEntry(**e) for e in json.loads(self.path.read_text())]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([asdict(e) for e in self.entries], indent=2))

    def add(self, raw: str, source: str = "retro", embedding: Optional[List[float]] = None) -> MemoryEntry:
        entry = MemoryEntry(
            id=f"mem_{len(self.entries) + 1}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            raw=raw,
            created_at=datetime.now(timezone.utc).isoformat(),
            embedding=embedding or [],
            source=source,
        )
        self.entries.append(entry)
        self.save()
        return entry

    def pull(self, window_days: int = PULL_WINDOW_DAYS, limit: int = RETRIEVAL_TOP_K) -> List[MemoryEntry]:
        """Pull recent memories within window. Mirrors khoj pull_memories (adapters:2287)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        recent = [
            e for e in self.entries
            if datetime.fromisoformat(e.created_at) >= cutoff
        ]
        # Sort by recency desc, khoj pattern: order_by("-created_at")[:limit]
        recent.sort(key=lambda e: e.created_at, reverse=True)
        return recent[:limit]

    def search(self, query: str, limit: int = RETRIEVAL_TOP_K) -> List[MemoryEntry]:
        """Stub: substring match. khoj uses pgvector cosine similarity.
        v0.1 keeps it simple; production should use real embeddings.
        """
        query_lower = query.lower()
        scored = [(sum(1 for w in query_lower.split() if w in e.raw.lower()), e) for e in self.entries]
        scored = [(s, e) for s, e in scored if s > 0]
        scored.sort(reverse=True)
        return [e for _, e in scored[:limit]]
