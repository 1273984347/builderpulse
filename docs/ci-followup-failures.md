# CI Follow-up: Test Failures

**Status (2026-06-06, end of day):** ✅ **All 11 originally-documented
failures are now resolved.** This document is kept for historical
context and as a record of the bug archaeology. See "Resolution" section
below for what was fixed.

---

## Context (original problem)

`fix(ci): use PEP 517 setuptools.build_meta backend` (commit 44b8048) got CI
past the install step. `chore(lint): pass ruff check + ruff format --check`
(commit 0a44e36) cleared the lint step. `fix(ci): declare missing test deps +
portable mock pattern` (commit 01aa187) got the test pass rate from 414/446 to
435/446 (32 → 11 failures). At that point the remaining 11 failures were
documented here.

## The 11 originally-remaining failures

### Category 1: Optional-extras tests run without the extra installed

CI installs only `[dev]`. Tests that need other extras failed with
`ModuleNotFoundError`.

| Failing tests | Missing extra |
|---|---|
| `test_source_scrapers.py::TestBlogSource` (×3) | `feedparser`, `beautifulsoup4` |
| `test_source_scrapers.py::TestTwitterSource::test_fetch_nitter_no_bearer_token` | `feedparser` |
| `test_source_scrapers.py::TestYouTubeSource` (×5) | `feedparser` |

### Category 2: LLM translation mock returns English, test expects Chinese

`tests/test_pipeline_remix.py::TestStepTranslate` (×2). Root cause: the
test mocked `Translator` but not `get_provider`, so on CI without
`openai` installed, `get_provider()` raised ImportError → fallback path
→ `ctx.translation = original` (English), not the expected Chinese.

### Category 3: FFmpeg missing on Windows/macOS CI runners

`test_transcribers.py::test_get_transcriber_unknown_engine` and
`test_get_transcriber_auto_no_engines` failed on Windows. Root cause:
`get_transcriber()` checked `find_ffmpeg()` BEFORE validating the
engine name, so `get_transcriber("nonexistent")` on a host without
ffmpeg raised `RuntimeError("FFmpeg not found")` instead of
`ValueError("Unknown engine")`. (Linux/macOS CI had ffmpeg installed
via brew/apt, so this only surfaced on Windows.)

## Resolution

All three categories fixed across the following commits:

| Commit | What it fixed |
|---|---|
| `1955690` | Added `feedparser` + `beautifulsoup4` to `[dev]` deps; reordered ffmpeg check in `_load_engine`; added `get_provider` mock to translate tests |
| `f0ba371` | First ffmpeg-order fix attempt (placed check before engine import — wrong order for auto loop semantics) |
| `697ac0b` | Root-cause fix: probe PyPI package directly via `importlib.import_module(pypi_pkg)` before the ffmpeg check, so the auto loop's `except ImportError` correctly catches "engine not installed" before it sees "ffmpeg missing" |

Final test pass rate: **446 passed, 2 skipped, 0 failed** (local venv +
CI 9/9 jobs).

## Lessons (for next debugging session)

1. **Single-platform verification hides Windows-specific bugs.** The
   original fix `1955690` was tested locally on Windows (Python 3.12)
   and passed, then failed on CI Windows (Python 3.10.11). The reason
   was a different order-of-operations issue that only mattered on
   platforms without ffmpeg.

2. **Source module presence ≠ PyPI package presence.**
   `from .faster_whisper import FasterWhisperTranscriber` always
   succeeds because `engines/transcribers/faster_whisper.py` is a
   *source* file in the project. To check if the engine is *actually
   usable*, probe the top-level PyPI package with
   `importlib.import_module("faster_whisper")` instead.

3. **Mock what the production code actually calls.** The LLM test
   mocked `Translator` but the production code calls `get_provider()`
   *before* instantiating `Translator`. The test was effectively
   mocking the wrong layer. Follow the existing `TestStepSummarize`
   pattern (which mocks `get_provider`).

4. **Cheap checks before expensive checks.** `get_transcriber()` was
   originally doing ffmpeg check first (expensive: subprocess call)
   before validating the engine name (cheap: set lookup). Inverting
   the order surfaces clearer errors to callers and avoids running
   ffmpeg probes for invalid engine names.
