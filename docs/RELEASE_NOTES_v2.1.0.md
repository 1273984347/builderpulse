# BuilderPulse v2.1.0

> **4 new sources + 4 new channels** — what we track, where we send.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)]()
[![Tests: 519 passing](https://img.shields.io/badge/tests-519%20passing-brightgreen.svg)]()

---

## The 30-Second Version

```bash
pip install --upgrade builderpulse
bp config show   # see "Newly available integrations" — opt in
```

You can now track **4 new content sources** and deliver to **4 new channels**.
New sources/channels are **disabled by default** to avoid credential-noise;
opt in explicitly via `bp config set enabled_sources+=<name>` or use
`bp config migrate --interactive` to walk through each one.

---

## What's New in v2.1.0

v2.1 turns BuilderPulse from a working v2.0 into a **true extensibility platform**:
you can track what you want, deliver where you want, and the system auto-protects
itself from misbehaving integrations.

### 4 New Sources (5 → 9 total)

| # | Source | Region | Type | Auth needed |
|:--|:-------|:-------|:-----|:------------|
| 1 | **GitHub Trending + Releases** | global | HTML scrape + REST API | Optional `github_token` for higher rate limit |
| 2 | **Twitch VODs** | global | Helix API | `client_id` + `client_secret` (OAuth Client Credentials) |
| 3 | **小红书 Xiaohongshu** | Chinese | HTML scrape (via Sogou proxy) | `proxy_url` strongly recommended |
| 4 | **公众号 WeChat MP** | Chinese | HTML scrape (via Sogou proxy) | `sogou_proxy` strongly recommended |

### 4 New Channels (8 → 12 total)

| # | Channel | Type | Auth needed |
|:--|:--------|:-----|:------------|
| 1 | **Generic Webhook** | HTTP POST/PUT/etc. JSON | `url` |
| 2 | **Slack** | Incoming Webhook | `webhook_url` |
| 3 | **Notion Database** | Notion API | `token` (Internal Integration) + `database_id` |
| 4 | **Apple Bark** | iOS push | `device_key` |

### New Behaviors

- **`bp config show` — Newly available integrations section**: lists v2.1.0 sources/channels
  not in your `enabled_sources`/`enabled_channels`. One-line description per integration.
- **`bp config migrate --interactive` wizard**: walks through each new integration asking
  enable/configure or skip. Recommended for first-time v2.1.0 users.
- **Experimental auto-disable**: Xiaohongshu and WeChat MP (marked `__experimental__`) are
  automatically disabled after 3 consecutive fetch failures within 1 hour. Prevents
  anti-scraping IP bans from cascading into digest failures.
- **Runtime state persistence**: auto-disable state is persisted to
  `~/.builderpulse/.runtime_state.json` so restarts don't reset the 1-hour
  failure window.

### Internal Improvements

- **PluginRegistry** gains `list(group, enabled_only)` and `list_all(group)` methods —
  powers the new "Newly available" CLI section and lays groundwork for v2.2+ Plugin
  Marketplace.
- **BatchManager** gains `run(sources_override=..., channels_override=...)` — temporarily
  fetch from a disabled source/channel without modifying `config.json`. Safety checks
  ensure experimental sources and credentialed channels can't be overridden without
  proper config.
- **Config schema** now tracks `__version__`. v2.0.0 configs auto-migrate on first load.
  Field-absent vs field-empty are now distinguished (explicit user choice respected).
- **Smoke test infrastructure**: nightly `.github/workflows/smoke.yml` runs
  `@pytest.mark.smoke` tests against real APIs using GitHub Secrets
  (`SMOKE_TWITCH_CLIENT_ID`, `SMOKE_NOTION_TOKEN`, etc.).
- **Helper scripts**: `scripts/check_entry_points_sorted.py` + `check_pyproject_format.py`
  (Python 3.9+ via `tomli` fallback) prevent merge conflicts on `pyproject.toml`
  when multiple agents add entry_points.

---

## 30-Second Migration Guide

```bash
pip install --upgrade builderpulse
bp config show
# Look for "Newly available integrations" — that's the new v2.1.0 stuff
bp config migrate --interactive
# Or opt in manually:
bp config set enabled_sources+=github_trending
bp config set enabled_sources+=twitch
# etc.
```

**Important:** v2.1.0 does NOT auto-enable new sources/channels. Your v2.0.0 config's
`enabled_sources` and `enabled_channels` lists are preserved as-is. This avoids surprise
credential errors for sources that need API keys you haven't configured.

### Configuration changes between v2.0.0 and v2.1.0

```diff
{
+ "__version__": "2.1.0",
  "enabled_sources": ["bilibili", "youtube", "podcast", "blog", "twitter"],
  "enabled_channels": ["telegram", "email", "feishu", "dingtalk", "discord", "wechat", "wecom", "stderr"],
+ "sources_config": {
+   "github_trending": {"languages": ["python"], "repos": [], "github_token": null},
+   "twitch": {"client_id": null, "client_secret": null, "channel_logins": []},
+   "xiaohongshu": {"user_ids": [], "proxy_url": null},
+   "wechat_mp": {"mp_names": [], "sogou_proxy": null}
+ },
+ "channels_config": {
+   "webhook": {"url": null, "method": "POST"},
+   "slack": {"webhook_url": null, "channel": "#general"},
+   "notion": {"token": null, "database_id": null},
+   "bark": {"device_key": null, "server": "https://api.day.app"}
+ }
}
```

`Config.from_file()` migrates your v2.0.0 config automatically on first load. Existing
fields are preserved (including your explicit `[]` choices).

### New CLI commands

| Command | Description |
|:--------|:------------|
| `bp config show` | Show effective config + **newly available integrations** section |
| `bp config migrate` | Migrate v2.0.0 → v2.1.0 config (auto on first load; this is a no-op) |
| `bp config migrate --interactive` | Walk through each new integration asking enable/skip |
| `bp config set enabled_sources+=<name>` | Opt in to a source |
| `bp config set enabled_channels+=<name>` | Opt in to a channel |
| `bp digest --source twitch --source bilibili` | One-shot override: fetch from these sources only |

---

## What you need to know

### 1. New sources are disabled by default

We deliberately did NOT pre-enable Xiaohongshu/WeChat MP/Twitch/etc. because
they require API keys/proxies you likely don't have configured. Auto-enabling would
cause digest failures and `SOURCE_MISSING_CREDENTIALS` log spam.

**What to do:** Run `bp config migrate --interactive` after upgrading. Or read
the [config docs](docs/sources/) for each source.

### 2. GitHub token is optional but recommended

GitHub Trending HTML scraping works without a token (60 req/hour). If you add
`repos = ["owner/repo", ...]` to track releases, GitHub REST API rate limit
becomes relevant. Set `github_token` in `sources_config.github_trending` for
5000 req/hour.

### 3. Experimental sources are protected

Xiaohongshu and WeChat MP are marked `__experimental__` because they scrape
public web pages with no public API. If the page structure changes or you get
rate-limited, the source **auto-disables after 3 consecutive failures within
1 hour** — your digest won't fail, you'll just see `(none)` for those sources.

To re-enable: `bp config set enabled_sources+=xiaohongshu` after fixing the
underlying issue (proxy config, etc.).

### 4. Subagent-driven development

v2.1.0's 8 new integrations were developed by 8 subagents in parallel.
Each subagent wrote its own PR with feature-branch entry_points + `__init__.py`
re-exports. A final "Registration batch PR" (Task 23) consolidated all 8 into
`pyproject.toml` and the manual `_CHANNELS` registry.

This pattern continues in v2.2.0 (Plugin Marketplace) and beyond.

---

## Migration from v2.0.0

**Automatic on first load.** No user action required.

Your v2.0.0 config:
```json
{
  "secrets_path": "/home/you/.builderpulse/secrets.json"
}
```

After first v2.1.0 load, becomes:
```json
{
  "__version__": "2.1.0",
  "secrets_path": "/home/you/.builderpulse/secrets.json",
  "enabled_sources": ["bilibili", "youtube", "podcast", "blog", "twitter"],
  "enabled_channels": ["telegram", "email", "feishu", "dingtalk", "discord", "wechat", "wecom", "stderr"],
  "sources_config": {},
  "channels_config": {}
}
```

**Idempotent.** Once `__version__: "2.1.0"` is in your config, subsequent
loads don't re-migrate. If you downgrade to v2.0.0 and re-upgrade, the
config is still considered v2.1.0 (no re-migration), preserving your
explicit choices.

### Rollback

If v2.1.0 has a critical bug, options:

1. **PyPI yank** (24h): `gh release edit v2.1.0 --yank` or PyPI Web UI → Version
   → Yank. Users on `pip install builderpulse` will fall back to v2.0.0.
2. **Emergency config disable**: `bp config set enabled_sources=["bilibili",
   "youtube", "podcast", "blog", "twitter"]` to restore v2.0.0 behavior
   without code downgrade.
3. **Pin version**: `pip install builderpulse==2.0.0` to lock to v2.0.0
   until v2.1.1 ships.

See [Rollback SOP](docs/operations/rollback.md) (TBD — to be written in
v2.1.1).

---

## Full Changelog

### Added
- 4 new sources: GitHub Trending + Releases, Twitch VODs, 小红书, 公众号
- 4 new channels: Slack, Notion Database, Generic Webhook, Apple Bark
- Registry API: `list(group, enabled_only)`, `list_all(group)`
- BatchManager: `run(sources_override, channels_override)`
- Config: `__version__` field + automatic migration
- CLI: `bp config show` lists "Newly available integrations"
- CLI: `bp config migrate --interactive` wizard
- ExperimentalPluginProxy: 3-failures-in-1h auto-disable for experimental sources
- Runtime state persistence: `~/.builderpulse/.runtime_state.json`
- Nightly smoke workflow: `.github/workflows/smoke.yml`
- Helper scripts: `scripts/check_entry_points_sorted.py` + `check_pyproject_format.py`
- Error codes: `SOURCE_MISSING_CREDENTIALS`, `SOURCE_AUTO_DISABLED`,
  `CHANNEL_DISABLED`
- Helper: `emit_error()` for structured error events

### Changed
- WBI key caching (in v2.0.1, but config schema changes affect v2.1.0 docs)
- Notion uses Internal Integration Token (no OAuth)
- `__init__.py` files now re-export v2.1.0 sources/channels (alphabetical)
- pyproject.toml now requires `pyproject.toml` entry-point registration
  for all v2.1.0 sources/channels (alphabetical, validated by `check_entry_points_sorted.py`)

### Fixed
- WBI cache thread safety + invalidation on -6 (v2.0.1)
- Twitch token refresh thundering-herd prevention (`threading.Lock` + 5s cooldown)
- Concurrent digest runs are safe (tested with `threading.Barrier`)
- CI matrix now 12/12 (was 9/9 in earlier notes; 9 was ci.yml, 12 is test.yml)
- Re-targeting PRs to non-default branch (e.g. `release/v2.0.1-v2.1.0`)
  doesn't trigger CI (spec gap, documented for future)

### Internal
- All 5 v2.0.0 sources (bilibili, blog, podcast, twitter, youtube) gained
  `name = "..."` class attribute required by `SourcePlugin` Protocol
- Internal: `ExperimentalPluginProxy` wraps any plugin with
  `__experimental__ = True` class attribute
- All 8 new integrations use Protocol duck-typing (not ABC inheritance)
  for consistency with existing codebase

---

## Try it

```bash
# Quickest start
pip install --upgrade builderpulse
bp config show
bp config migrate --interactive

# Or: opt in to specific integrations
bp config set enabled_sources+=github_trending
bp config set enabled_sources+=twitch  # (also set client_id + client_secret first)
bp config set enabled_channels+=notion  # (also set token + database_id)
bp config set enabled_channels+=slack  # (also set webhook_url)

# Or: one-shot override for testing
bp digest --source twitch --deliver notion

# Optional extras (pick what you need)
pip install builderpulse[github]   # for github_trending (uses beautifulsoup4)
pip install builderpulse[twitch]   # for twitch (httpx + socks for proxy)
pip install builderpulse[all-coverage]  # everything at once
```

**Config examples** in [`docs/sources/`](docs/sources/) and
[`docs/channels/`](docs/channels/) (TBD — to be added per-integration
in v2.1.0+ follow-up).

---

## Acknowledgments

v2.1.0's 8 new integrations were built using the subagent-driven-development
pattern: 8 parallel implementation subagents, each with isolated context,
writing tests first, opening a PR per integration. A final "Registration batch"
subagent consolidated all 8 into `pyproject.toml`. This pattern enables
"weekly minor releases" going forward — each new integration is a 1-3 day
subagent task rather than a 1-2 week human effort.

Spec: [`docs/superpowers/specs/2026-06-07-builderpulse-v2-roadmap-design.md`](docs/superpowers/specs/2026-06-07-builderpulse-v2-roadmap-design.md)
Plan: [`docs/superpowers/plans/2026-06-07-builderpulse-v2-roadmap-implementation.md`](docs/superpowers/plans/2026-06-07-builderpulse-v2-roadmap-implementation.md)
