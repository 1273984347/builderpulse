# Error Codes Reference

BuilderPulse uses string error codes for programmatic error identification. Codes are JSON-safe and human-readable.

## Core Error Codes

| Code | Phase | Description |
|:-----|:------|:------------|
| `DOWNLOAD_FAILED` | Download | General download failure (network, HTTP error) |
| `DOWNLOAD_TIMEOUT` | Download | Download exceeded time limit |
| `DOWNLOAD_FORBIDDEN` | Download | HTTP 403 or permission denied |
| `TRANSCRIBE_FAILED` | Transcribe | General transcription failure |
| `TRANSCRIBE_NO_AUDIO` | Transcribe | No audio track found in media |
| `TRANSCRIBE_ENGINE_UNAVAILABLE` | Transcribe | Selected engine not installed or failed to init |
| `SUMMARIZE_FAILED` | Summarize | LLM summarization failed |
| `SUMMARIZE_QUOTA_EXCEEDED` | Summarize | API quota/rate limit hit |
| `TRANSLATE_FAILED` | Translate | Translation step failed |
| `DELIVER_FAILED` | Deliver | General delivery failure |
| `DELIVER_RATE_LIMITED` | Deliver | Delivery channel rate-limited the request |
| `BATCH_ITEM_FAILED` | Batch | Single item in batch processing failed |
| `BATCH_DISK_FULL` | Batch | Disk space exhausted during batch |
| `CONFIG_NOT_FOUND` | Config | Config file missing at expected path |
| `CONFIG_INVALID` | Config | Config file has invalid JSON or missing required fields |

## Plugin Error Codes

Plugin error codes follow the format:

```
PLUGIN_{plugin_name}_{code}
```

- `plugin_name` and `code` are uppercased automatically
- Example: `PLUGIN_MYDOWNLOADER_NETWORK_ERROR`

### Registering Plugin Error Codes

```python
from builderpulse.core.error_codes import register_plugin_code

# Register a custom error code
full_code = register_plugin_code(
    plugin="mydownloader",
    code="network_error",
    desc="Network connection failed during download",
)
# full_code == "PLUGIN_MYDOWNLOADER_NETWORK_ERROR"
```

Registration is idempotent — re-registering the same plugin+code is safe.

### Querying Error Info

```python
from builderpulse.core.error_codes import get_error_info

# Core code
info = get_error_info("DOWNLOAD_FAILED")
# {"type": "core", "code": "DOWNLOAD_FAILED"}

# Plugin code
info = get_error_info("PLUGIN_MYDOWNLOADER_NETWORK_ERROR")
# {"type": "plugin", "plugin": "mydownloader", "code": "NETWORK_ERROR", "description": "..."}

# Unknown code
info = get_error_info("UNKNOWN_THING")
# {"type": "unknown", "code": "UNKNOWN_THING"}
```

## Error Classification in BatchManager

`BatchManager._classify_error()` maps exceptions to error codes by walking the `__cause__` chain:

| Exception Type | Error Code |
|:---------------|:-----------|
| `DiskFullError` | `BATCH_DISK_FULL` |
| `PermissionError` | `DOWNLOAD_FORBIDDEN` |
| `RetryExhausted` (with ConnectionError history) | `BATCH_ITEM_FAILED` |
| `RetryExhausted` (with TimeoutError history) | `BATCH_ITEM_FAILED` |
| Other exceptions | `BATCH_ITEM_FAILED` |

## Troubleshooting

### DOWNLOAD_FAILED
- Check network connectivity
- Verify the URL is accessible
- Check if the site requires authentication (set `sessdata` for Bilibili)

### DOWNLOAD_TIMEOUT
- Increase timeout in downloader configuration
- Check if the file is unusually large
- Verify network stability

### TRANSCRIBE_ENGINE_UNAVAILABLE
- Install the required engine: `pip install builderpulse[faster-whisper]`
- Check that ffmpeg is available on PATH
- Verify GPU drivers if using whisperx

### CONFIG_NOT_FOUND
- Run `bp config init` to create a config file
- Check `~/.builderpulse/config.json` exists
- Verify `BUILDERPULSE_CONFIG_PATH` env var if set

### BATCH_DISK_FULL
- Free disk space or increase `min_disk_bytes` threshold
- Run `bp clean` to remove old output files
- Check the workspace directory has sufficient space

### DELIVER_RATE_LIMITED
- Wait and retry later
- Check delivery channel API quotas
- Consider using a different delivery channel
