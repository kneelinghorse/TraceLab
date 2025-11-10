"""Tests for TokenManager."""

from cli.utils.auth import TokenManager


def test_token_manager_persists_and_expires(tmp_path):
    token_dir = tmp_path / "tokens"
    manager = TokenManager(token_dir=token_dir)

    manager.save_token("abc123", expires_in=120)
    assert manager.is_authenticated()
    assert manager.get_token() == "abc123"

    manager.save_token("expired", expires_in=-10)
    assert manager.get_token() is None
    assert not manager.is_authenticated()
