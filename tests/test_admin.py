from app.models import UserRole
from tests.conftest import login, make_user


async def test_admin_routes_forbidden_for_users(client, db):
    u = await make_user(db, "plainuser@vyronmail.com", role=UserRole.USER)
    await login(client, u.effective_email)
    r = await client.get("/api/admin/dashboard")
    assert r.status_code == 403
    r = await client.get("/api/admin/users")
    assert r.status_code == 403


async def test_admin_dashboard_ok(client, db):
    u = await make_user(db, "rootadmin@vyronmail.com", role=UserRole.ADMIN)
    await login(client, u.effective_email)
    r = await client.get("/api/admin/dashboard")
    assert r.status_code == 200, r.text
    assert "metrics" in r.json()


async def test_anon_admin_forbidden(client, db):
    from tests.conftest import _build_client
    async with _build_client() as c2:
        r = await c2.get("/api/admin/dashboard")
        assert r.status_code == 401
