# Migration Guide: v1 to v2

## Compatibility Matrix

| Feature | v1 Behavior | v2 Behavior |
|:--------|:------------|:------------|
| Config loading | `Config()` reads from fixed path | `ConfigManager` singleton with hot-reload |
| Config override | Manual editing only | Env vars (`BUILDERPULSE_*`) override all fields |
| Error handling | String error messages | `ErrorCode` enum + plugin codes |
| Batch processing | None | `BatchManager` with cache, rate limiter, disk guard |
| Plugin system | None | Entry-point based with Protocol validation |
| MCP server | Basic stdio | Full JSON-RPC with 8 tools |
| Observability | None | OpenTelemetry tracer + meter (optional) |
| Progress display | Print statements | Rich progress bars with ETA |
| Secret handling | Plaintext in config | Auto-masked in `to_dict()`, keyring support |
| Retry logic | None | Exponential backoff (sync + async) |

## Config Field Mapping

| v1 Field | v2 Field | Notes |
|:---------|:---------|:------|
| `sources.bilibili.enabled` | `sources.bilibili.enabled` | Unchanged |
| `sources.bilibili.users` | `sources.bilibili.users` | Unchanged |
| `delivery.method` | `delivery.method` | Unchanged |
| `delivery.telegram.botToken` | `telegram_bot_token` (env) | Also accessible via `BUILDERPULSE_TELEGRAM_BOT_TOKEN` |
| `engine` | `engine` | Unchanged; `auto` selects best available |
| N/A | `model` | New: transcription model size |
| N/A | `device` | New: `auto`/`cpu`/`cuda` |

## Downgrade Scenarios

### Scenario 1: Config incompatibility

If v2 config fields cause issues with v1:

```bash
# 1. Export current config
bp config show > config-v2-backup.json

# 2. Edit config to remove v2-only fields
# Remove: model, device, workspace, cleanup
# Keep: language, engine, sources, delivery

# 3. Downgrade package
pip install builderpulse==1.0.0
```

### Scenario 2: MCP server issues

If the MCP server fails with v2:

```bash
# 1. Use legacy pipeline mode
export BUILDERPULSE_LEGACY_PIPELINE=1

# 2. Or downgrade MCP entry point
pip install builderpulse==1.0.0

# 3. Verify MCP works
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | bp serve
```

### Scenario 3: Batch processing regression

If batch processing behaves differently:

```bash
# 1. Clear batch cache
rm -f batch_cache.db

# 2. Run single-item test
bp transcribe <url>

# 3. If still failing, downgrade
pip install builderpulse==1.0.0
```

## MCP Client Compatibility

### Claude Code

Add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "builderpulse": {
      "command": "bp",
      "args": ["serve"]
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "builderpulse": {
      "command": "bp",
      "args": ["serve"]
    }
  }
}
```

### Custom MCP Client

Connect via stdio with JSON-RPC 2.0:

```python
import subprocess, json

proc = subprocess.Popen(
    ["bp", "serve"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
)

# Send initialize
msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
header = f"Content-Length: {len(msg)}\r\n\r\n"
proc.stdin.write(header.encode() + msg.encode())
proc.stdin.flush()
```

## Legacy Mode

Set `BUILDERPULSE_LEGACY_PIPELINE=1` to use v1 pipeline behavior:

```bash
export BUILDERPULSE_LEGACY_PIPELINE=1
bp transcribe <url>
```

This bypasses:
- ConfigManager singleton (uses direct Config loading)
- Plugin registry (uses built-in sources only)
- BatchManager (processes URLs sequentially without cache)

Legacy mode is intended for troubleshooting only and will be removed in v3.
