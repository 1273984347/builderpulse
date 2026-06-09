# Release Checklist: BuilderPulse v2.1.0

**Date:** 2026-06-07 (spec written) | **Target release:** 2026-XX-XX
**Owner:** <user>
**PR tracker:** [GitHub PRs #10-#19, #18, plus Task 23 to be created]

---

## Pre-Merge Checklist (BEFORE tagging v2.1.0)

### Code & PRs

- [ ] **PR #10** (Week 0: Registry API, BatchManager, Config, ErrorCodes, CLI, smoke, scripts) — MERGED
- [ ] **PR #18** (FIX: ExperimentalPluginProxy) — MERGED  (CRITICAL: without this, Xiaohongshu/WeChat MP auto-disable won't work)
- [ ] **PR #11** (GitHub Trending) — MERGED
- [ ] **PR #12** (Twitch VODs) — MERGED
- [ ] **PR #13** (Generic Webhook) — MERGED
- [ ] **PR #14** (Apple Bark) — MERGED
- [ ] **PR #15** (Slack) — MERGED
- [ ] **PR #16** (Notion Database) — MERGED
- [ ] **PR #17** (Xiaohongshu — experimental) — MERGED
- [ ] **PR #19** (WeChat MP — experimental) — MERGED
- [ ] **Task 23: Registration batch PR** — OPENED, all 8 entry_points + 5 v2.0.0 source `name` additions, MERGED

### Final CI Status

- [ ] **CI green on master** (`test.yml` 12/12 jobs × 3 OS × 4 Python)
- [ ] **CodeQL scan** clean
- [ ] **Weekly dependabot** — no new alerts introduced this release

### Final Test Status (local)

- [ ] `pytest tests/ -x --ignore=tests/test_transcribers.py -q` — 519+ tests pass, 0 regressions
- [ ] `ruff check src/ tests/` — all checks pass
- [ ] `ruff format --check src/ tests/` — all files formatted
- [ ] `scripts/check_entry_points_sorted.py` — OK
- [ ] `scripts/check_pyproject_format.py` — OK
- [ ] **Manual smoke test** of v2.1.0 end-to-end (run `bp config migrate --interactive`, then `bp digest` with 1-2 new integrations enabled)

### Configuration

- [ ] **Migration tested on a real v2.0.0 config**: copy a real v2.0.0 config.json to a test machine, run `bp config show` on v2.1.0, verify migration works
- [ ] **`__version__` field** present in migrated configs (`Config.from_file` adds it)
- [ ] **PyPI token** (`PYPI_TOKEN`) set in repo Settings → Secrets
- [ ] **GH_TOKEN** for releases (typically auto-provided by Actions) — verify release workflow has `permissions: contents: write`

---

## Release Day Steps

### 1. Create the tag

```bash
git checkout master
git pull
git log --oneline -10  # verify all 11 PRs are visible
git tag -a v2.1.0 -m "Release v2.1.0 — 4 new sources + 4 new channels

- 4 new sources: GitHub Trending + Releases, Twitch VODs, 小红书, 公众号
- 4 new channels: Slack, Notion Database, Generic Webhook, Apple Bark
- PluginRegistry: list() with enabled_only, list_all()
- BatchManager: run() with sources_override / channels_override
- Config: __version__ field + automatic migration
- CLI: 'Newly available' section in bp config show
- ExperimentalPluginProxy: 3-failures-in-1h auto-disable
- Helper scripts: entry_points sort + pyproject format check
- 519+ tests, 12/12 CI green on 3 OS × 4 Python"
git push origin v2.1.0
```

### 2. Monitor release workflow

```bash
gh run watch
```

The release.yml workflow will:
1. Build sdist + wheel
2. Create DRAFT GitHub Release
3. Publish to PyPI
4. Promote GH Release from draft to published

### 3. Verify PyPI publish

```bash
# Wait ~30 seconds, then:
curl -s https://pypi.org/pypi/builderpulse/json | python -c "import json, sys; d = json.load(sys.stdin); print('Latest:', d['info']['version']); print('Releases:', sorted(d['releases'].keys()))"
# Should show: Latest: 2.1.0
```

### 4. Verify GitHub Release

```bash
gh release view v2.1.0
# Should show release notes from docs/RELEASE_NOTES_v2.1.0.md
```

### 5. Install + test in a fresh venv

```bash
python -m venv /tmp/bp-test
source /tmp/bp-test/bin/activate
pip install --upgrade builderpulse==2.1.0
bp --version  # should show 2.1.0
bp config show  # should show "Newly available" section
bp digest --days 1  # should work (or skip if no enabled sources)
```

### 6. Update README and CHANGELOG (if needed)

- [ ] `CHANGELOG.md` — confirm `[2.1.0] - 2026-XX-XX` section is present and accurate
- [ ] `README.md` — confirm the "9 sources, 12 channels" counts are right
- [ ] `README.zh-CN.md` — sync

---

## Post-Release Monitoring (first 7 days)

### T+0 (immediately after release)

- [ ] **PyPI page live**: https://pypi.org/project/builderpulse/ shows v2.1.0
- [ ] **GH Release live**: https://github.com/1273984347/builderpulse/releases/tag/v2.1.0
- [ ] **`pip install builderpulse==2.1.0`** works
- [ ] **GH Actions: release workflow SUCCESS** (no failed steps)

### T+1h

- [ ] **HN post live** (if Wednesday 9am ET)
- [ ] **Twitter thread live**
- [ ] Monitor HN comments (active for 4h)

### T+1d

- [ ] **Reddit posts live** (r/Python, r/selfhosted, r/AItools)
- [ ] **Lobsters post live**
- [ ] **GitHub stars**: check for unusual spike
- [ ] **PyPI downloads**: check https://pypistats.org/packages/builderpulse

### T+1w

- [ ] **No critical bugs reported** in issues
- [ ] **Triage issues**: label `bug` / `enhancement` / `question` / `docs`
- [ ] **First patch** (if needed): plan v2.1.0.post1
- [ ] **Update launch doc** (`docs/launch/v2.1.0-launch.md`) with actual metrics

### T+1mo

- [ ] **Reflective retrospective**: 8D retrospective (per `feedback/retrospective-automation.md` pattern)
- [ ] **Update memory** with v2.1.0 lessons learned
- [ ] **Plan v2.1.1 or v2.2.0** based on feedback

---

## Rollback Plan (if critical bug found)

### Within 24h of release

1. **Yank from PyPI** (one of):
   ```bash
   # Via Web UI: https://pypi.org/manage/project/builderpulse/release/2.1.0/ → Options → Yank
   # Or via API:
   curl -X POST https://pypi.org/api/projects/builderpulse/2.1.0/yank -H "Authorization: token $PYPI_TOKEN"
   ```
2. **Mark GH release as pre-release** (so it's not "latest"):
   ```bash
   gh release edit v2.1.0 --pre-release
   ```
3. **Open a hotfix branch**, fix the bug, tag v2.1.0.post1
4. **Post in HN comment thread**: "We found a bug, here's the fix, here's the timeline"

### Beyond 24h (more risky)

1. **Don't yank** — too many users will be affected
2. **Release v2.1.0.post1** with the fix
3. **Mark v2.1.0 as "known issue" in release notes** for the post1
4. **Communicate in HN/Twitter**: explain the post1 + thank users for finding

---

## Notes for Future Releases (v2.2.0+)

- The 8-PR pattern (4 sources + 4 channels) scales well — apply for any
  "ecosystem expansion" release
- v2.1.0's auto-disable for experimental sources is the right pattern;
  add to v2.2.0's Plugin v2 sandbox
- Pre-merge Task 23 (Registration batch) is a critical step — it
  consolidates 8 PRs into pyproject.toml without conflicts
- Subagent-driven development + 2-stage review (spec + code) is the
  right approach for repeated integration work
