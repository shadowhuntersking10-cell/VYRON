"""Health endpoints + the i18n system (3 locales, identical key sets, no blanks)."""

from __future__ import annotations


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_ready_checks_mysql_and_redis(client):
    res = client.get("/ready")
    assert res.status_code == 200
    checks = res.json()["checks"]
    assert checks["database"] == "ok"
    assert checks["redis"] == "ok"


def test_i18n_catalogs_have_identical_key_sets():
    from vyron.i18n import SUPPORTED_LANGUAGES, catalog, flatten

    flats = {lang: set(flatten(catalog(lang))) for lang in SUPPORTED_LANGUAGES}
    reference = flats["en"]
    for lang, keys in flats.items():
        assert keys == reference, f"{lang} differs: missing={sorted(reference - keys)[:5]} extra={sorted(keys - reference)[:5]}"
    assert len(reference) > 600


def test_i18n_no_blank_values():
    from vyron.i18n import SUPPORTED_LANGUAGES, catalog, flatten

    for lang in SUPPORTED_LANGUAGES:
        for key, value in flatten(catalog(lang)).items():
            assert str(value).strip(), f"blank translation {lang}:{key}"


def test_t_falls_back_to_english_then_key():
    from vyron.i18n import t

    assert t("nav.home", "uz") != "nav.home"
    assert t("definitely.missing.key", "uz") == "definitely.missing.key"
    assert "{name}" not in t("miniapp.greeting", "en", name="Ali")


def test_i18n_api_returns_catalog(client):
    for lang in ("uz", "en", "ru"):
        res = client.get(f"/api/i18n/{lang}")
        assert res.status_code == 200
        assert res.json()["success"] is True


def test_default_language_is_uzbek():
    from vyron.i18n import DEFAULT_LANGUAGE

    assert DEFAULT_LANGUAGE == "uz"
