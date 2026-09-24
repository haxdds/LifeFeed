from datetime import datetime, timedelta, timezone

from app.routers.feed import score

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def post(client, user, content="hello", **extra):
    r = client.post("/api/posts", json={"content": content, **extra}, headers=user["headers"])
    assert r.status_code == 201, r.text
    return r.json()


# --- auth -------------------------------------------------------------------


def test_register_login_and_me(client, make_user):
    alice = make_user("alice")
    assert alice["display_name"] == "alice"

    r = client.post("/api/auth/login", json={"username": "ALICE", "password": "password123"})
    assert r.status_code == 200
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert r.json()["username"] == "alice"


def test_register_rejects_duplicates_and_bad_input(client, make_user):
    make_user("alice")
    r = client.post("/api/auth/register", json={"username": "Alice", "password": "password123"})
    assert r.status_code == 409
    r = client.post("/api/auth/register", json={"username": "a b", "password": "password123"})
    assert r.status_code == 422
    r = client.post("/api/auth/register", json={"username": "bob", "password": "short"})
    assert r.status_code == 422


def test_bad_credentials_and_tokens(client, make_user):
    make_user("alice")
    r = client.post("/api/auth/login", json={"username": "alice", "password": "wrong-password"})
    assert r.status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


# --- posts ------------------------------------------------------------------


def test_create_get_delete_post(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    p = post(client, alice, "  first post  ")
    assert p["content"] == "first post"

    assert client.get(f"/api/posts/{p['id']}").json()["author"]["username"] == "alice"
    assert client.delete(f"/api/posts/{p['id']}", headers=bob["headers"]).status_code == 403
    assert client.delete(f"/api/posts/{p['id']}", headers=alice["headers"]).status_code == 204
    assert client.get(f"/api/posts/{p['id']}").status_code == 404


def test_post_validation(client, make_user):
    alice = make_user("alice")
    h = alice["headers"]
    assert client.post("/api/posts", json={"content": "   "}, headers=h).status_code == 422
    assert client.post("/api/posts", json={"content": "x" * 281}, headers=h).status_code == 422
    r = client.post("/api/posts", json={"content": "hi", "media_url": "http://evil/x.png"}, headers=h)
    assert r.status_code == 400
    assert client.post("/api/posts", json={"content": "hi"}).status_code == 401


def test_replies_and_thread(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    root = post(client, alice, "root")
    reply = post(client, bob, "reply", reply_to_id=root["id"])
    nested = post(client, alice, "nested", reply_to_id=reply["id"])

    assert reply["reply_to_username"] == "alice"
    assert client.get(f"/api/posts/{root['id']}").json()["reply_count"] == 1
    replies = client.get(f"/api/posts/{root['id']}/replies").json()["items"]
    assert [r["id"] for r in replies] == [reply["id"]]
    thread = client.get(f"/api/posts/{nested['id']}/thread").json()
    assert [p["id"] for p in thread] == [root["id"], reply["id"]]

    client.delete(f"/api/posts/{reply['id']}", headers=bob["headers"])
    assert client.get(f"/api/posts/{root['id']}").json()["reply_count"] == 0
    assert client.get(f"/api/posts/{nested['id']}").status_code == 404  # cascaded


def test_like_unlike_is_idempotent(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    p = post(client, alice)
    for _ in range(2):
        r = client.post(f"/api/posts/{p['id']}/like", headers=bob["headers"])
    assert r.json()["like_count"] == 1 and r.json()["liked_by_me"]
    assert client.get(f"/api/posts/{p['id']}", headers=alice["headers"]).json()["liked_by_me"] is False

    likes = client.get("/api/users/bob/likes").json()["items"]
    assert [x["id"] for x in likes] == [p["id"]]

    for _ in range(2):
        r = client.delete(f"/api/posts/{p['id']}/like", headers=bob["headers"])
    assert r.json()["like_count"] == 0 and not r.json()["liked_by_me"]


def test_repost_and_unrepost(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    p = post(client, alice)
    for _ in range(2):
        r = client.post(f"/api/posts/{p['id']}/repost", headers=bob["headers"])
    assert r.json()["repost_count"] == 1 and r.json()["reposted_by_me"]

    timeline = client.get("/api/users/bob/posts", headers=bob["headers"]).json()["items"]
    assert len(timeline) == 1
    repost = timeline[0]
    assert repost["repost_of"]["id"] == p["id"] and repost["repost_of"]["reposted_by_me"]

    # Acting on the repost row targets the original.
    r = client.post(f"/api/posts/{repost['id']}/like", headers=alice["headers"])
    assert r.json()["id"] == p["id"] and r.json()["like_count"] == 1

    r = client.delete(f"/api/posts/{p['id']}/repost", headers=bob["headers"])
    assert r.json()["repost_count"] == 0
    assert client.get("/api/users/bob/posts").json()["items"] == []


def test_deleting_original_removes_reposts(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    p = post(client, alice)
    client.post(f"/api/posts/{p['id']}/repost", headers=bob["headers"])
    client.delete(f"/api/posts/{p['id']}", headers=alice["headers"])
    assert client.get("/api/users/bob/posts").json()["items"] == []


# --- users & follows --------------------------------------------------------


def test_follow_unfollow_and_profile(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    r = client.post("/api/users/bob/follow", headers=alice["headers"])
    assert r.json()["is_following"] and r.json()["follower_count"] == 1
    client.post("/api/users/bob/follow", headers=alice["headers"])  # idempotent

    profile = client.get("/api/users/alice", headers=bob["headers"]).json()
    assert profile["follows_you"] and profile["following_count"] == 1

    followers = client.get("/api/users/bob/followers").json()["items"]
    assert [u["username"] for u in followers] == ["alice"]
    following = client.get("/api/users/alice/following").json()["items"]
    assert [u["username"] for u in following] == ["bob"]

    r = client.delete("/api/users/bob/follow", headers=alice["headers"])
    assert not r.json()["is_following"] and r.json()["follower_count"] == 0

    assert client.post("/api/users/alice/follow", headers=alice["headers"]).status_code == 400
    assert client.get("/api/users/nobody").status_code == 404


def test_update_profile_and_search(client, make_user):
    alice = make_user("alice")
    r = client.patch(
        "/api/users/me", json={"display_name": "Alice A.", "bio": "hi there"}, headers=alice["headers"]
    )
    assert r.json()["display_name"] == "Alice A." and r.json()["bio"] == "hi there"
    assert [u["username"] for u in client.get("/api/users?q=alice a").json()] == ["alice"]
    r = client.patch("/api/users/me", json={"avatar_url": "/media/missing.png"}, headers=alice["headers"])
    assert r.status_code == 400


def test_suggestions_exclude_self_and_followed(client, make_user):
    alice, _bob, _carol = make_user("alice"), make_user("bob"), make_user("carol")
    client.post("/api/users/bob/follow", headers=alice["headers"])
    names = [u["username"] for u in client.get("/api/users/suggestions", headers=alice["headers"]).json()]
    assert names == ["carol"]


# --- feed -------------------------------------------------------------------


def test_chronological_feed(client, make_user):
    alice, bob, carol = make_user("alice"), make_user("bob"), make_user("carol")
    client.post("/api/users/bob/follow", headers=alice["headers"])
    mine = post(client, alice, "mine")
    bobs = post(client, bob, "bob's")
    post(client, carol, "carol's (not followed)")
    post(client, bob, "a reply", reply_to_id=mine["id"])  # replies stay out of the home feed
    client.post(f"/api/posts/{mine['id']}/repost", headers=bob["headers"])

    feed = client.get("/api/feed", headers=alice["headers"]).json()
    kinds = [(p["author"]["username"], (p["repost_of"] or {}).get("id")) for p in feed["items"]]
    assert kinds == [("bob", mine["id"]), ("bob", None), ("alice", None)]
    assert feed["items"][1]["id"] == bobs["id"]


def test_feed_pagination(client, make_user):
    alice = make_user("alice")
    ids = [post(client, alice, f"post {i}")["id"] for i in range(5)]
    seen, cursor = [], None
    while True:
        params = {"limit": 2, **({"cursor": cursor} if cursor else {})}
        page = client.get("/api/feed", params=params, headers=alice["headers"]).json()
        seen += [p["id"] for p in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == list(reversed(ids))
    assert client.get("/api/feed?cursor=abc", headers=alice["headers"]).status_code == 400


def test_ranked_feed_orders_by_engagement(client, make_user):
    alice, bob, carol = make_user("alice"), make_user("bob"), make_user("carol")
    client.post("/api/users/bob/follow", headers=alice["headers"])
    boring = post(client, bob, "boring")
    popular = post(client, bob, "popular")
    older_hit = post(client, bob, "older hit")
    for u in (alice, carol):
        client.post(f"/api/posts/{older_hit['id']}/like", headers=u["headers"])
        client.post(f"/api/posts/{older_hit['id']}/repost", headers=u["headers"])

    page = client.get("/api/feed?mode=ranked&limit=10", headers=alice["headers"]).json()
    ids = [(p["repost_of"] or p)["id"] for p in page["items"]]
    assert ids[0] == older_hit["id"]
    assert set(ids) == {boring["id"], popular["id"], older_hit["id"]}  # repost deduped


def test_ranked_feed_is_cached_and_invalidated(client, make_user):
    alice = make_user("alice")
    post(client, alice, "one")
    assert len(client.get("/api/feed?mode=ranked", headers=alice["headers"]).json()["items"]) == 1
    post(client, alice, "two")  # own post invalidates own cache
    assert len(client.get("/api/feed?mode=ranked", headers=alice["headers"]).json()["items"]) == 2


def test_score_decays_with_age():
    assert score(10, 0, 0, 1) > score(10, 0, 0, 48)
    assert score(0, 5, 0, 5) > score(5, 0, 0, 5)


def test_explore_lists_everyone(client, make_user):
    alice, bob = make_user("alice"), make_user("bob")
    post(client, alice, "a")
    b = post(client, bob, "b")
    post(client, bob, "reply", reply_to_id=b["id"])
    items = client.get("/api/posts").json()["items"]
    assert [p["content"] for p in items] == ["b", "a"]


def test_timestamps_are_utc(client, make_user):
    p = post(client, make_user("alice"))
    created = datetime.fromisoformat(p["created_at"].replace("Z", "+00:00"))
    assert created.utcoffset() == timedelta(0)
    assert abs(datetime.now(timezone.utc) - created) < timedelta(minutes=1)


# --- media ------------------------------------------------------------------


def test_media_upload_and_attach(client, make_user):
    alice = make_user("alice")
    r = client.post(
        "/api/media", files={"file": ("pic.png", PNG, "image/png")}, headers=alice["headers"]
    )
    assert r.status_code == 201, r.text
    url = r.json()["url"]
    assert client.get(url).content == PNG

    p = post(client, alice, "", media_url=url)
    assert p["media_url"] == url
    r = client.patch("/api/users/me", json={"avatar_url": url}, headers=alice["headers"])
    assert r.json()["avatar_url"] == url


def test_media_upload_rejects_bad_files(client, make_user):
    h = make_user("alice")["headers"]
    r = client.post("/api/media", files={"file": ("x.txt", b"hello", "text/plain")}, headers=h)
    assert r.status_code == 415
    r = client.post("/api/media", files={"file": ("x.png", b"not a png", "image/png")}, headers=h)
    assert r.status_code == 400
    r = client.post("/api/media", files={"file": ("x.png", PNG, "image/png")})
    assert r.status_code == 401
