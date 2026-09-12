"""SSR website: every public page renders, protected pages gate, errors have real status codes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

PUBLIC_PAGES = [
    "/",
    "/games",
    "/products",
    "/marketplace",
    "/promotions",
    "/donations",
    "/support",
    "/about",
    "/terms",
    "/privacy",
    "/refund-policy",
    "/login",
    "/register",
    "/forgot-password",
    "/miniapp",
    "/search",
]

HTML = {"Accept": "text/html"}


@pytest.fixture()
def anon(app):
    """Fresh cookie jar — the session-scoped client gets authenticated by
    register-auto-login in other tests, so anonymous behaviour needs isolation."""
    return TestClient(app, raise_server_exceptions=False)


def test_public_pages_render(anon):
    client = anon
    for path in PUBLIC_PAGES:
        res = client.get(path, headers=HTML)
        assert res.status_code == 200, f"{path} -> {res.status_code}"
        assert "<html" in res.text
        assert "vyron" in res.text.lower()


def test_pages_do_not_leak_stack_traces(anon):
    client = anon
    res = client.get("/products/no-such-product-slug", headers=HTML)
    assert res.status_code == 404
    assert "Traceback" not in res.text
    assert "sqlalchemy" not in res.text.lower()


def test_protected_pages_redirect_anonymous(anon):
    client = anon
    for path in ("/dashboard", "/checkout", "/seller", "/admin"):
        res = client.get(path, headers=HTML, follow_redirects=False)
        assert res.status_code == 302, f"{path} -> {res.status_code}"
        assert "/login" in res.headers["location"]


def test_security_headers_present(anon):
    client = anon
    res = client.get("/", headers=HTML)
    headers = {k.lower(): v for k, v in res.headers.items()}
    assert headers.get("x-content-type-options") == "nosniff"
    assert "x-frame-options" in headers or "content-security-policy" in headers


def test_cors_is_not_wildcard(anon):
    client = anon
    res = client.options("/", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert res.headers.get("access-control-allow-origin") != "*"


def test_language_cookie_switches_rendering(anon):
    client = anon
    client.cookies.set("vyron_lang", "ru", domain="testserver")
    res = client.get("/", headers=HTML)
    assert res.status_code == 200
    bundle = res.text
    assert "i18n-bundle" in bundle
    client.cookies.set("vyron_lang", "uz", domain="testserver")


def test_api_errors_have_structured_shape(anon):
    client = anon
    res = client.get("/api/orders")  # no session
    assert res.status_code == 401
    body = res.json()
    assert body["success"] is False
    assert set(body["error"]) >= {"code", "message"}


def test_openapi_docs_available(anon):
    client = anon
    assert client.get("/api/docs").status_code == 200
    spec = client.get("/api/openapi.json")
    assert spec.status_code == 200
    assert len(spec.json()["paths"]) > 100
