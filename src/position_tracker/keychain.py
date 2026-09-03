"""Credential and session storage backed by the OS keychain.

Per CLAUDE.md: credentials and session tokens must never be written to a
plaintext local file. The OS keychain (via `keyring`) is the one approved
place to persist them.
"""

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

import keyring

_SERVICE = "position-tracker"


def _session_username(firm: str) -> str:
    return f"{firm}:session"


def save_session(firm: str, session_state: dict[str, Any]) -> None:
    """Persist a Playwright storage_state dict, tagged with the time it was captured."""
    payload = {"captured_at": datetime.now(UTC).isoformat(), "state": session_state}
    keyring.set_password(_SERVICE, _session_username(firm), json.dumps(payload))


def load_session(firm: str, ttl_seconds: int) -> dict[str, Any] | None:
    """Return the cached Playwright storage_state for a firm, or None if absent/expired."""
    raw = keyring.get_password(_SERVICE, _session_username(firm))
    if raw is None:
        return None

    payload = json.loads(raw)
    captured_at = datetime.fromisoformat(payload["captured_at"])
    age_seconds = (datetime.now(UTC) - captured_at).total_seconds()
    if age_seconds > ttl_seconds:
        return None

    state: dict[str, Any] = payload["state"]
    return state


def clear_session(firm: str) -> None:
    with contextlib.suppress(keyring.errors.PasswordDeleteError):
        keyring.delete_password(_SERVICE, _session_username(firm))
