# Migration Guide: BuilderPulse v2.0.0 → v2.1.0

**Last updated:** 2026-06-07
**Target audience:** Existing v2.0.0 users upgrading to v2.1.0
**Estimated migration time:** 5-15 minutes (mostly reading + opt-in decisions)

---

## TL;DR

```bash
pip install --upgrade builderpulse
bp config show   # ← look for "Newly available integrations" section
bp config migrate --interactive
```

That's it. v2.0.0 configs auto-migrate on first load. New integrations are
disabled by default. You opt in to what you want.

---

## What changes (and what doesn't)

### ✅ No breaking changes

- **Your v2.0.0 config is preserved.** `enabled_sources` and `enabled_channels`
  keep your existing values. v2.1.0 only ADDS new fields.
- **Your existing digest flow still works.** v2.0.0 sources/channels function
  identically. No behavior changes.
- **No new required dependencies.** All v2.1.0 new integrations are optional
  extras (`pip install builderpulse[github]` etc.).
- **CLI commands backward-compatible.** All v2.0.0 commands work identically.
  v2.1.0 only ADDS new commands (`config migrate --interactive`,
  `config show`'s new section).

### ⚠️ Configuration additions (auto-applied)

Your `config.json` gains these new fields (auto-filled on first v2.1.0 load):

| Field | Default | Purpose |
|:------|:--------|:--------|
| `__version__` | `"2.1.0"` | Migration tracking — prevents re-migration on subsequent loads |
| `sources_config` | `{}` | Per-source settings (credentials, rate limits) for v2.1.0 sources |
| `channels_config` | `{}` | Per-channel settings for v2.1.0 channels |

These are added **without** removing or modifying your existing fields. Your
explicit `enabled_sources = []` is preserved (not overwritten with defaults).

### 🆕 New opt-in integrations

| Source/Channel | What you need to do | Time |
|:---------------|:---------------------|:-----|
| GitHub Trending | Just enable (works without token) | 30s |
| Twitch VODs | Enable + set `client_id` + `client_secret` | 2min |
| 小红书 Xiaohongshu | Enable + configure `proxy_url` (Sogou recommended) | 5min |
| 公众号 WeChat MP | Enable + configure `sogou_proxy` | 5min |
| Generic Webhook | Enable + set `url` | 30s |
| Slack | Enable + set `webhook_url` (Slack Incoming Webhook) | 1min |
| Notion Database | Enable + set `token` + `database_id` | 3min |
| Apple Bark | Enable + set `device_key` | 1min |

---

## Step-by-step migration

### Step 1: Upgrade

```bash
pip install --upgrade builderpulse
```

Verify version:

```bash
bp --version
# Should show 2.1.0
```

### Step 2: First run auto-migrates your config

```bash
bp config show
```

This will:
1. Read your existing v2.0.0 `config.json`
2. Detect missing `__version__` field
3. Fill in `__version__: "2.1.0"` + new empty `sources_config` / `channels_config`
4. Write the updated config back to disk
5. Display the config + new "Newly available integrations" section

**Your existing `enabled_sources` and `enabled_channels` lists are unchanged.**

### Step 3: Discover what's new

`bp config show` output now has a "Newly available integrations" section:

```
# Newly available integrations (v2.1.0, disabled by default):
#   Sources: github_trending, twitch, xiaohongshu, wechat_mp
#     Enable: bp config set enabled_sources+=<name>
#   Channels: slack, notion, webhook, bark
#     Enable: bp config set enabled_channels+=<name>
```

### Step 4: Opt in (interactive or manual)

**Option A — interactive wizard (recommended for first migration):**

```bash
bp config migrate --interactive
```

Walks through each new integration:

```
Found 4 new sources and 4 new channels.

Enable source 'github_trending'? [y/N]: y
  -> Added github_trending to enabled_sources.
Enable source 'twitch'? [y/N]: n
Enable source 'xiaohongshu'? [y/N]: n
  WARNING: experimental; needs proxy_url config.
...

Updated /home/you/.builderpulse/config.json
```

**Option B — manual:**

```bash
# Enable sources
bp config set enabled_sources+=github_trending
bp config set enabled_sources+=twitch
# (then set client_id + client_secret — see below)
bp config set enabled_sources+=xiaohongshu  # experimental — needs proxy

# Enable channels
bp config set enabled_channels+=webhook
bp config set enabled_channels+=slack
# (then set webhook_url — see below)
```

### Step 5: Configure credentials

After enabling, configure per-integration settings:

**GitHub (works without credentials, but token recommended for higher rate):**
```bash
bp config set sources_config.github_trending.github_token=ghp_your_token
# Optional:
bp config set sources_config.github_trending.languages='["python","rust"]'
bp config set sources_config.github_trending.repos='["owner/repo"]'
```

**Twitch (requires OAuth Client Credentials):**
1. Go to https://dev.twitch.tv/console/apps
2. Register a new app, get `client_id` and `client_secret`
3. ```bash
   bp config set sources_config.twitch.client_id=your_client_id
   bp config set sources_config.twitch.client_secret=your_client_secret
   bp config set sources_config.twitch.channel_logins='["anthropic","openai"]'
   ```

**Slack:**
1. Go to https://api.slack.com/apps → your app → Incoming Webhooks
2. Create a webhook, copy the URL
3. ```bash
   bp config set channels_config.slack.webhook_url=https://hooks.slack.com/services/...
   ```

**Notion:**
1. Go to https://www.notion.so/my-integrations
2. Create internal integration, get token
3. Share a database with the integration
4. Get the database ID from the URL
5. ```bash
   bp config set channels_config.notion.token=ntn_...
   bp config set channels_config.notion.database_id=your_db_id
   ```

**Apple Bark:**
1. Install Bark iOS app
2. Get your device key
3. ```bash
   bp config set channels_config.bark.device_key=your_key
   ```

**Xiaohongshu (experimental, proxy strongly recommended):**
```bash
bp config set sources_config.xiaohongshu.user_ids='["user_id_1"]'
bp config set sources_config.xiaohongshu.proxy_url=socks5://localhost:1080
```

**WeChat MP (experimental, Sogou proxy strongly recommended):**
```bash
bp config set sources_config.wechat_mp.mp_names='["公众号名"]'
bp config set sources_config.wechat_mp.sogou_proxy=https://weixin.sogou.com/...
```

**Generic Webhook:**
```bash
bp config set channels_config.webhook.url=https://your-endpoint.example.com/builderpulse
# Optional: custom method, headers
bp config set channels_config.webhook.method=PUT
```

### Step 6: Verify

```bash
bp config show
```

Check:
1. Your `enabled_sources` now includes the ones you opted in for
2. `sources_config` has the credentials set (redacted in display)
3. `__version__` is `"2.1.0"`

```bash
bp digest --days 1
```

Should run without errors. Sources you haven't enabled (or can't reach) will
be skipped with a warning.

---

## Troubleshooting

### My digest is slower after upgrade

If you enabled Xiaohongshu/WeChat MP without a proxy, those sources will
auto-disable after 3 failures in 1 hour (per spec §3.10). This is by design —
without a proxy, those scrapers get IP-banned quickly.

**Solution:** Configure a proxy (Sogou proxy or commercial scraping API).

### `bp config show` shows weird output

If the JSON formatting looks off, your `config.json` may have been edited
manually with inconsistent formatting. Run:

```bash
python -c "import json; print(json.dumps(json.load(open('/home/you/.builderpulse/config.json')), indent=2))"
```

This reformats it.

### I want to disable an integration again

```bash
bp config set enabled_sources-=xiaohongshu
bp config set enabled_channels-=slack
```

(The `-=` operator removes from the list.)

### Auto-disabled experimental source — how to re-enable

If Xiaohongshu/WeChat MP auto-disabled (after 3 failures):

1. Fix the underlying issue (add proxy, etc.)
2. Re-enable manually:
   ```bash
   bp config set enabled_sources+=xiaohongshu
   ```
3. The auto-disable state is in `~/.builderpulse/.runtime_state.json`. It will
   reset after the 1-hour window OR you can delete the file to reset immediately.

### Rollback to v2.0.0

If v2.1.0 has a critical bug:

```bash
pip install builderpulse==2.0.0
```

Your v2.1.0 config is forward-compatible with v2.0.0 (v2.0.0 ignores the new
fields). v2.1.0 features simply won't be available, but existing functionality
works.

---

## Field reference

### `__version__`

- Type: string
- Format: `"X.Y.Z"` (e.g., `"2.1.0"`)
- Comparison: string lexicographic (works correctly for `X.Y.Z` format)
- Set automatically on first v2.1.0 load; do NOT edit manually

### `enabled_sources` / `enabled_channels`

- Type: list of strings
- Default (v2.0.0 → v2.1.0 migration): `["bilibili","youtube","podcast","blog","twitter"]`
  / `["telegram","email","feishu","dingtalk","discord","wechat","wecom","stderr"]`
- v2.1.0 NEW sources/channels: NOT in default — must opt in explicitly

### `sources_config`

- Type: dict mapping source name → dict of settings
- v2.0.0: empty `{}`
- v2.1.0: per-source settings (e.g., `{"github_trending": {"github_token": "..."}}`)
- Schema: see [`docs/sources/<name>.md`](docs/sources/) per source

### `channels_config`

- Type: dict mapping channel name → dict of settings
- v2.0.0: empty `{}`
- v2.1.0: per-channel settings (e.g., `{"slack": {"webhook_url": "..."}}`)
- Schema: see [`docs/channels/<name>.md`](docs/channels/) per channel

---

## What about v2.2.0?

v2.2.0 is **planned** (Q4 2026 estimate, not committed) and will focus on:
- Plugin v2: sandboxed plugins, official plugin list
- MCP depth: HTTP transport, OAuth, multi-server routing
- Performance: batch speedup, Whisper real E2E

See [Roadmap](docs/ROADMAP.md) (TBD) for details.

For v2.1.x patches, see [CHANGELOG.md](CHANGELOG.md).

---

## Getting help

- **Documentation**: [docs/](docs/)
- **Issue tracker**: https://github.com/1273984347/builderpulse/issues
- **Discussions**: https://github.com/1273984347/builderpulse/discussions

For migration issues, open an issue with the `migration` label.
