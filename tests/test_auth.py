from tests.conftest import login, make_user


async def test_register_login_me(client, db):
    r = await client.post("/api/auth/register", json={"email": "newreg@vyronmail.com", "password": "Password123"})
    assert r.status_code == 200, r.text
    r = await client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "newreg@vyronmail.com"


async def test_register_duplicate_rejected(client, db):
    u = await make_user(db, "dup@vyronmail.com")
    r = await client.post("/api/auth/register", json={"email": u.effective_email, "password": "Password123"})
    assert r.status_code == 400


async def test_login_wrong_password(client, db):
    u = await make_user(db, "w@vyronmail.com")
    r = await client.post("/api/auth/login", json={"login": u.effective_email, "password": "WrongPass1"})
    assert r.status_code == 401


async def test_logout(client, db):
    u = await make_user(db, "lo@vyronmail.com")
    await login(client, u.effective_email)
    r = await client.post("/api/auth/logout")
    assert r.status_code == 200
    # new client without cookie
    from tests.conftest import _build_client
    async with _build_client() as c2:
        r = await c2.get("/api/auth/me")
        assert r.status_code == 401


async def test_password_never_plain(client, db):
    u = await make_user(db, "h@vyronmail.com", password="Secret1234")
    assert u.password_hash != "Secret1234"
    assert len(u.password_hash) > 20
