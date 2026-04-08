from httpx import AsyncClient


# ---------------------------------------------------------------------------
# POST /links/shorten
# ---------------------------------------------------------------------------

async def test_shorten_anonymous(client: AsyncClient):
    resp = await client.post("/links/shorten", json={"url": "https://example.com"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["short_code"], str) and len(body["short_code"]) == 6


async def test_shorten_custom_alias(client: AsyncClient):
    resp = await client.post("/links/shorten", json={"url": "https://example.com", "custom_alias": "mylink"})
    assert resp.status_code == 200
    assert resp.json()["short_code"] == "mylink"


async def test_shorten_duplicate_alias_returns_failure(client: AsyncClient):
    await client.post("/links/shorten", json={"url": "https://a.com", "custom_alias": "dup"})
    resp = await client.post("/links/shorten", json={"url": "https://b.com", "custom_alias": "dup"})
    assert resp.status_code == 200
    assert resp.json()["success"] is False


async def test_shorten_authenticated(auth_client: AsyncClient):
    resp = await auth_client.post("/links/shorten", json={"url": "https://example.com"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ---------------------------------------------------------------------------
# GET /{short_code}  — redirect
# ---------------------------------------------------------------------------

async def test_redirect_existing_link(client: AsyncClient):
    create = await client.post("/links/shorten", json={"url": "https://target.com", "custom_alias": "go"})
    assert create.json()["success"] is True
    resp = await client.get("/links/go", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://target.com"


async def test_redirect_unknown_code_returns_error(client: AsyncClient):
    resp = await client.get("/links/doesnotexist", follow_redirects=False)
    assert resp.status_code == 200
    assert "error" in resp.json()


# ---------------------------------------------------------------------------
# GET /{short_code}/stats
# ---------------------------------------------------------------------------

async def test_stats_existing_link(client: AsyncClient):
    await client.post("/links/shorten", json={"url": "https://stats.com", "custom_alias": "st"})
    resp = await client.get("/links/st/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["original_url"] == "https://stats.com"
    assert body["short_code"] == "st"
    assert "access_count" in body


async def test_stats_unknown_code_returns_404(client: AsyncClient):
    resp = await client.get("/links/nope00/stats")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /links/search
# ---------------------------------------------------------------------------

async def test_search_finds_link(client: AsyncClient):
    await client.post("/links/shorten", json={"url": "https://search.me", "custom_alias": "sr"})
    resp = await client.get("/links/search", params={"original_url": "https://search.me"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert any(r["short_code"] == "sr" for r in body["results"])


async def test_search_returns_empty_for_unknown(client: AsyncClient):
    resp = await client.get("/links/search", params={"original_url": "https://nothere.com"})
    assert resp.status_code == 200
    assert resp.json()["results"] == []


# ---------------------------------------------------------------------------
# DELETE /{short_code}
# ---------------------------------------------------------------------------

async def test_delete_own_link(auth_client: AsyncClient):
    await auth_client.post("/links/shorten", json={"url": "https://del.me", "custom_alias": "dl"})
    resp = await auth_client.delete("/links/dl")
    assert resp.status_code == 204


async def test_delete_unauthenticated_returns_401(client: AsyncClient):
    await client.post("/links/shorten", json={"url": "https://del.me", "custom_alias": "dl2"})
    resp = await client.delete("/links/dl2")
    assert resp.status_code == 401


async def test_delete_other_users_link_returns_404(auth_client: AsyncClient, db_session):
    from links.models import ShortLink # type: ignore
    from datetime import datetime, timedelta, timezone
    link = ShortLink(
        original_url="https://anon.com",
        short_code="anon",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(link)
    await db_session.commit()
    resp = await auth_client.delete("/links/anon")
    assert resp.status_code == 404


async def test_delete_nonexistent_link_returns_404(auth_client: AsyncClient):
    resp = await auth_client.delete("/links/nope00")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /{short_code}
# ---------------------------------------------------------------------------

async def test_update_own_link(auth_client: AsyncClient):
    await auth_client.post("/links/shorten", json={"url": "https://old.com", "custom_alias": "upd"})
    resp = await auth_client.put("/links/upd", params={"new_url": "https://new.com"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True


async def test_update_unauthenticated_returns_401(client: AsyncClient):
    await client.post("/links/shorten", json={"url": "https://old.com", "custom_alias": "upd2"})
    resp = await client.put("/links/upd2", params={"new_url": "https://new.com"})
    assert resp.status_code == 401


async def test_update_other_users_link_returns_failure(auth_client: AsyncClient, db_session):
    from links.models import ShortLink # type: ignore
    from datetime import datetime, timedelta, timezone
    link = ShortLink(
        original_url="https://anon.com",
        short_code="upd3",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(link)
    await db_session.commit()
    resp = await auth_client.put("/links/upd3", params={"new_url": "https://new.com"})
    assert resp.status_code == 200
    assert resp.json()["success"] is False


# ---------------------------------------------------------------------------
# POST /links/history
# ---------------------------------------------------------------------------

async def test_history_unauthenticated_returns_401(client: AsyncClient):
    resp = await client.post("/links/history", json={})
    assert resp.status_code == 401


async def test_history_empty_for_new_user(auth_client: AsyncClient):
    resp = await auth_client.post("/links/history", json={"page": 1, "limit": 20})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["results"] == []
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# Auth endpoints (register / login)
# ---------------------------------------------------------------------------

async def test_register_new_user(client: AsyncClient):
    resp = await client.post("/auth/register", json={"email": "new@example.com", "password": "securepass"})
    assert resp.status_code == 201
    assert resp.json()["email"] == "new@example.com"


async def test_register_duplicate_email_returns_400(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "securepass"}
    await client.post("/auth/register", json=payload)
    resp = await client.post("/auth/register", json=payload)
    assert resp.status_code == 400


async def test_login_returns_token(client: AsyncClient):
    await client.post("/auth/register", json={"email": "login@example.com", "password": "securepass"})
    resp = await client.post(
        "/auth/jwt/login",
        data={"username": "login@example.com", "password": "securepass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_login_wrong_password_returns_400(client: AsyncClient):
    await client.post("/auth/register", json={"email": "bad@example.com", "password": "securepass"})
    resp = await client.post(
        "/auth/jwt/login",
        data={"username": "bad@example.com", "password": "wrongpass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 400
