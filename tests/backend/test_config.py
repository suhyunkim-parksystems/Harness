from app.config import DEFAULT_CORS_ORIGIN_REGEX, load_settings


def test_default_cors_origin_regex_allows_local_network_origins(monkeypatch):
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)

    settings = load_settings()

    assert settings.cors_origin_regex == DEFAULT_CORS_ORIGIN_REGEX
    assert "192\\.168" in settings.cors_origin_regex
    assert "10(?:" in settings.cors_origin_regex
    assert "172\\." in settings.cors_origin_regex


def test_cors_origin_regex_can_be_disabled(monkeypatch):
    monkeypatch.setenv("CORS_ORIGIN_REGEX", "")

    settings = load_settings()

    assert settings.cors_origin_regex is None
