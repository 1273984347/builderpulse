# GitHub Secrets Required for Nightly Smoke

The nightly smoke workflow (`.github/workflows/smoke.yml`) runs at 3am UTC daily
and can be triggered manually via `workflow_dispatch`. It exercises live
integrations against read-only test accounts to catch upstream API drift
before users hit it.

## Required Secrets

Add the following to repo **Settings → Secrets and variables → Actions**:

| Secret name | Purpose |
|:------------|:--------|
| `SMOKE_TWITCH_CLIENT_ID` | Twitch app client ID (dev.twitch.tv) |
| `SMOKE_TWITCH_CLIENT_SECRET` | Twitch app client secret (same app as above) |
| `SMOKE_NOTION_TOKEN` | Notion internal integration token (read-only) |
| `SMOKE_NOTION_DATABASE_ID` | Notion test workspace database ID |
| `SMOKE_SLACK_WEBHOOK` | Slack Incoming Webhook URL for `#bp-smoke-test` channel |
| `SMOKE_BARK_DEVICE_KEY` | Bark (iOS push) test device key |
| `SMOKE_WEBHOOK_URL` | Echo server URL (e.g. `https://httpbin.org/post`) |

All credentials are **READ-ONLY** test accounts. Never use real user credentials.

The workflow exposes each secret to the test process using the unprefixed env
var name (e.g. `SMOKE_TWITCH_CLIENT_ID` → `TWITCH_CLIENT_ID`). Tests should
read them via `os.environ.get(...)` and gracefully skip when unset.

## If a Secret is Missing

If a smoke test references a missing secret, mark the test as
`@pytest.mark.xfail(strict=False)` and add a comment explaining the missing
secret. **Do NOT mark the test as `@pytest.mark.skip`** — silent skip loses
the test coverage signal and the missing-secret issue becomes invisible.

Pattern for tests requiring optional secrets:

```python
import os
import pytest


@pytest.mark.smoke
def test_twitch_health_live():
    if not os.environ.get("TWITCH_CLIENT_ID"):
        pytest.skip("TWITCH_CLIENT_ID not set in this environment")
    # ... real call ...
```

## Verifying the Workflow Locally

You can simulate the smoke run without GitHub by setting the env vars and
invoking pytest directly:

```bash
export TWITCH_CLIENT_ID=...
export TWITCH_CLIENT_SECRET=...
# ... etc ...
pytest -m smoke --tb=short -v
```

Or invoke the workflow manually from the GitHub Actions tab → "Nightly Smoke"
→ "Run workflow".
