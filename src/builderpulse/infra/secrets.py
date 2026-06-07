"""Secret storage with 3-tier fallback: env var -> keyring -> secrets.json."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SECRETS_DIR = Path.home() / ".builderpulse"
SECRETS_FILE = SECRETS_DIR / "secrets.json"
SERVICE_NAME = "builderpulse"

SENSITIVE_KEYS = {
    "telegram_bot_token",
    "api_key",
    "api_secret",
    "sessdata",
    "smtp_password",
    "resend_api_key",
    "x_bearer_token",
}


def get_secret(key: str) -> str | None:
    """Read secret: env var -> keyring -> secrets.json."""
    # 1. Environment variable (highest priority)
    env_key = f"BUILDERPULSE_{key.upper()}"
    env_val = os.environ.get(env_key)
    if env_val:
        return env_val

    # 2. Keyring (desktop users)
    try:
        import keyring

        val = keyring.get_password(SERVICE_NAME, key)
        if val:
            return val
    except Exception:
        pass

    # 3. secrets.json (fallback)
    if SECRETS_FILE.exists():
        try:
            data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
            return data.get(key)
        except (json.JSONDecodeError, OSError):
            pass

    return None


def set_secret(key: str, value: str) -> None:
    """Store secret: try keyring first, fallback to secrets.json."""
    # Try keyring
    try:
        import keyring

        keyring.set_password(SERVICE_NAME, key, value)
        return
    except Exception:
        pass

    # Fallback: secrets.json with chmod 600
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    data: dict[str, str] = {}
    if SECRETS_FILE.exists():
        try:
            data = json.loads(SECRETS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    data[key] = value
    # P2 fix: atomic write
    tmp_path = SECRETS_FILE.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(str(tmp_path), str(SECRETS_FILE))

    # Set permissions (Unix only)
    if sys.platform != "win32":
        os.chmod(SECRETS_FILE, 0o600)
    else:
        # P2 fix: Windows ACL — inherit default DACL is too permissive
        # (Users group typically has Read). Attempt icacls to restrict to
        # current user only. If icacls is not on PATH, just warn.
        import logging

        _log = logging.getLogger("builderpulse.secrets")
        import shutil
        import subprocess

        icacls = shutil.which("icacls")
        if not icacls:
            _log.warning(
                "icacls not found on PATH; secrets.json may inherit permissive "
                "ACLs. Install/run on a system with icacls, or move the file "
                "to a user-only directory manually."
            )
        else:
            try:
                username = os.environ.get("USERNAME") or os.environ.get("USER") or ""
                if username:
                    # /inheritance:r  — remove inherited ACLs
                    # /grant:r USER:(R,W) — grant current user R/W only
                    subprocess.run(
                        [
                            icacls,
                            str(SECRETS_FILE),
                            "/inheritance:r",
                            f"/grant:r {username}:(R,W)",
                        ],
                        check=True,
                        capture_output=True,
                        timeout=10,
                    )
                else:
                    _log.warning(
                        "Could not determine current user (USERNAME/USER); "
                        "leaving secrets.json ACLs unchanged."
                    )
            except (
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                OSError,
            ) as exc:
                _log.warning("icacls failed for secrets.json: %s", exc)


def mask_value(value: str | None) -> str:
    """Mask a secret value for display."""
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def is_sensitive(key: str) -> bool:
    """Check if a key is sensitive."""
    return key.lower() in SENSITIVE_KEYS
