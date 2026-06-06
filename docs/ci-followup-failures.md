# CI Follow-up: Remaining Test Failures

**Status (2026-06-06):** v2.0.0 has 11 remaining test failures in CI that this
PR did **not** address. They are documented here for the next pass.

## Context

`fix(ci): use PEP 517 setuptools.build_meta backend` (commit 44b8048) got CI
past the install step. `chore(lint): pass ruff check + ruff format --check`
(commit 0a44e36) cleared the lint step. `fix(ci): declare missing test deps +
portable mock pattern` (commit 01aa187) got the test pass rate from 414/446 to
435/446 (32 → 11 failures).

The 11 remaining failures fall into 3 categories below. None of them is in
scope for the immediate CI-green push, but they will block `Release` workflow
runs and degrade confidence in test signal.

## Category 1: Optional-extras tests run without the extra installed

CI installs only `[dev]`. Tests that need other extras fail with
`ModuleNotFoundError`.

| Failing tests | Missing extra | Why it's missing |
|---|---|---|
| `test_source_scrapers.py::TestBlogSource` (×3) | `feedparser`, `beautifulsoup4` | in `[sources]`, not `[dev]` |
| `test_source_scrapers.py::TestTwitterSource::test_fetch_nitter_no_bearer_token` | `feedparser` | in `[sources]`, not `[dev]` |
| `test_source_scrapers.py::TestYouTubeSource` (×5) | `feedparser` | in `[sources]`, not `[dev]` |
| `test_transcribers.py::*` (whisper) | `whisper` / `faster-whisper` | in their own extras (ML models, GBs) |

**Two reasonable fixes:**

1. **Widen CI install to all extras** in `.github/workflows/ci.yml`:
   `pip install -e ".[dev,sources,mcp,llm]"` plus skip heavy ML extras.
   Pro: one-line change. Con: CI time increases (whisper pulls torch ~1 GB).

2. **Add `pytest.importorskip` to each test that needs an extra**, and
   CI stays slim. Pro: tests self-skip cleanly. Con: more invasive, touches
   ~10 test files.

**Recommendation:** option 1 for the small deps (`feedparser`,
`beautifulsoup4`, `tweepy`, `mcp`, `openai`, `anthropic`, `ollama`); skip
the ML extras in CI via `@pytest.mark.slow` or similar, and let them run
on-demand or locally only.

## Category 2: LLM translation mock returns English, test expects Chinese

`tests/test_pipeline_remix.py::TestStepTranslate` (×2) fails with:

```
AssertionError: assert 'English summary' == '中文摘要'
```

The mock fixture in `test_pipeline_remix.py` is hard-coding language to
`en` or not respecting the `language` field on the config. Two tests
expect Chinese output but receive the English fallback.

This is a **test-side bug**: the mock is not language-aware. The fix is
to either (a) make the mock return-language-aware or (b) change the
assertion to use whatever language the test sets up. (~5-line change in
`tests/test_pipeline_remix.py`.)

**Status:** requires reading the mock fixture carefully. Skipped for now.

## Category 3: FFmpeg missing on Windows/macOS CI runners

`tests/test_*` that needs FFmpeg fails with:

```
RuntimeError: FFmpeg not found. Install it: https://ffmpeg.org/download.html
```

`ci.yml` only installs FFmpeg on Ubuntu (`if: runner.os == 'Linux'`). On
`windows-latest` and `macos-latest`, the corresponding `Install system
dependencies` step is `if: runner.os == 'macOS'` and installs via brew —
but that step is skipped on Windows.

**Fix:** add a Windows FFmpeg install step, or `skip` the FFmpeg-requiring
tests on non-Linux via `@pytest.mark.skipif(sys.platform == "win32", ...)`.

**Status:** not investigated which test specifically needs it on Windows.

## Reproducing locally

```bash
python -m venv .venv-test
.venv-test/Scripts/python.exe -m pip install -e ".[dev]"
.venv-test/Scripts/python.exe -m pytest tests/ --tb=line
```

Expect: 11 failed, 435 passed, 2 skipped. The 2 skipped are
platform-conditional tests; the 11 failed match the categories above.

## Suggested next pass

1. Add `feedparser`, `beautifulsoup4` to `[dev]` (small deps, used in
   tests that don't need full sources behavior).
2. Fix the LLM mock language awareness (~5 lines).
3. Add `skipif(sys.platform == "win32", ...)` to FFmpeg test or
   install FFmpeg on Windows runner.

Estimated effort: 30-60 minutes. Should get to 0 failed / 2 skipped.
