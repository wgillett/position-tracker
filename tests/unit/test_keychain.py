import keyring
import pytest

from position_tracker import keychain


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], str]:
    """Swap the OS keychain for an in-memory dict so tests don't touch the real one."""
    store: dict[tuple[str, str], str] = {}

    def fake_set(service: str, username: str, password: str) -> None:
        store[(service, username)] = password

    def fake_get(service: str, username: str) -> str | None:
        return store.get((service, username))

    def fake_delete(service: str, username: str) -> None:
        try:
            del store[(service, username)]
        except KeyError as exc:
            raise keyring.errors.PasswordDeleteError from exc

    monkeypatch.setattr(keyring, "set_password", fake_set)
    monkeypatch.setattr(keyring, "get_password", fake_get)
    monkeypatch.setattr(keyring, "delete_password", fake_delete)
    return store


def test_save_and_load_session_roundtrip() -> None:
    state = {"cookies": [{"name": "session", "value": "abc"}]}

    keychain.save_session("fidelity", state)
    loaded = keychain.load_session("fidelity", ttl_seconds=3600)

    assert loaded == state


def test_load_session_returns_none_when_expired() -> None:
    keychain.save_session("fidelity", {"cookies": []})

    loaded = keychain.load_session("fidelity", ttl_seconds=-1)

    assert loaded is None


def test_load_session_returns_none_when_absent() -> None:
    assert keychain.load_session("nonexistent-firm", ttl_seconds=3600) is None


def test_clear_session_removes_stored_value() -> None:
    keychain.save_session("fidelity", {"cookies": []})

    keychain.clear_session("fidelity")

    assert keychain.load_session("fidelity", ttl_seconds=3600) is None


def test_clear_session_absent_is_a_no_op() -> None:
    keychain.clear_session("nonexistent-firm")
