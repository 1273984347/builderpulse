# Concurrency Writing Checklist

When writing or reviewing code that handles shared state, verify:

## Thread Safety

- [ ] All writes to shared state are guarded by `threading.Lock` (or `RLock` if reentrant)
- [ ] Read-modify-write sequences are atomic (no TOCTOU between check and act)
- [ ] Cache invalidation is atomic with the next read (no torn read)

## Async Safety

- [ ] `asyncio.Lock` (not `threading.Lock`) guards async-shared state
- [ ] No `await` inside a critical section holding a `threading.Lock` (deadlock risk)
- [ ] Background tasks (e.g., periodic refresh) are cancelled on shutdown

## Database (SQLite WAL)

- [ ] `BEGIN IMMEDIATE` (or `EXCLUSIVE`) for write transactions that depend on read state
- [ ] `INSERT OR IGNORE` for idempotent inserts (avoid TOCTOU `SELECT` then `INSERT`)
- [ ] `state.mark_processed()` and `state.cursor_update()` are wrapped in `_lock()`

## Process Boundaries

- [ ] File writes are atomic (write to `tmp` + `os.replace`)
- [ ] Config writes go through `ConfigManager.set_config_path()` (single source of truth)
- [ ] No direct `json.dump(config, file)` outside `ConfigManager`

## Examples in this codebase

- `src/builderpulse/core/shared_utils.py`: WBI cache uses `threading.Lock` (added in v2.0.1)
- `src/builderpulse/sources/twitch.py`: token cache uses `threading.Lock` (added in v2.1.0)
- `src/builderpulse/plugins/registry.py`: plugin loading uses `threading.Lock` for thread safety
- `src/builderpulse/core/state.py`: cursor updates and `mark_processed` use `_lock()` (per codebase pattern)

## When Reviewing Concurrency Code

Ask:
1. **Who can read this state concurrently?** (other threads? other async tasks? other processes?)
2. **Who can write?** (same set as readers? fewer?)
3. **What invariants must hold?** (e.g., "cursor is always set to a non-null value after first fetch")
4. **Can the invariant be broken by interleaving?** If yes, the operation needs a lock.
5. **What happens if the operation fails partway?** (e.g., exception during `_replace` after `os.remove`)

If any of these are unclear, the code is too clever; simplify before merging.
