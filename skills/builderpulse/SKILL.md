---
name: builderpulse
description: |
  AI builder content aggregation and video transcription.
  Use when: transcribe video, AI digest, builder updates, B站字幕, 抖音转录, 播客摘要, video to text
  Boundaries: Only for content aggregation and transcription tasks
triggers:
  - transcribe video
  - video to text
  - AI digest
  - builder updates
  - B站字幕
  - 抖音转录
  - 播客摘要
  - bp digest
  - bp transcribe
  - builder pulse
  - content aggregation
  - video transcription
---

# BuilderPulse Skill

AI builder content aggregation and video transcription tool.

## Step 0: Check installation

```bash
BP_BIN=$(which bp 2>/dev/null || echo "")
[ -z "$BP_BIN" ] && echo "NOT_FOUND" || echo "FOUND: $BP_BIN"
```

If `NOT_FOUND`: tell user "BuilderPulse not installed. Run: `pip install builderpulse`" and stop.

## Step 1: Detect intent

Parse the user's message to determine which command to run:

| Intent | Command |
|:-------|:--------|
| Transcribe a video/audio URL | `bp transcribe <url>` |
| Batch transcribe a creator | `bp batch <user_url>` |
| Generate AI digest | `bp digest [options]` |
| Fetch raw content | `bp fetch <source>` |
| End-to-end pipeline | `bp process <url>` |
| Clean old files | `bp clean` |
| Show/set config | `bp config show/set` |
| Start MCP server | `bp serve` |

## Step 2: Execute

Run the appropriate `bp` command with timeout:

```bash
timeout 120 bp <command> <args> 2>&1
```

For long operations (transcribe, digest), use `run_in_background` and notify user when done.

## Step 3: Present results

- Transcription: show word count + first 500 chars of text
- Digest: show item count + titles
- Fetch: show item count + sample titles
- Errors: show error message + suggest fix

## Step 4: Offer follow-up

After completing the main task, offer related actions:
- "Want me to summarize this transcript?"
- "Want me to deliver this to Telegram?"
- "Want me to fetch more content from other sources?"

## MCP Mode

If user asks to use BuilderPulse as an MCP tool, configure:

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

Or for dedicated MCP entry point:
```json
{
  "mcpServers": {
    "builderpulse": {
      "command": "builderpulse-mcp"
    }
  }
}
```
