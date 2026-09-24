# LifeFeed

A Twitter clone built as a practice project: posts, replies, reposts, likes, follows, a home feed (chronological + ranked), user profiles and image uploads. Everything runs locally. It needs no cloud services and no Docker.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.10 and the dependencies for you).

```bash
cd backend
uv sync                        # install dependencies
uv run python -m app.seed      # optional: demo users + posts (password: password123)
uv run main.py                 # http://127.0.0.1:8000  (add --reload while developing)
```

Open http://127.0.0.1:8000 for the web app, or http://127.0.0.1:8000/docs for the interactive API docs.

Run the tests:

```bash
cd backend && uv run pytest
```

## Stack

| Concern  | Local default                          | Optional swap-in (env var)                   |
|----------|----------------------------------------|----------------------------------------------|
| API      | Python, FastAPI + Uvicorn              |                                              |
| Database | SQLite file `backend/lifefeed.db`      | PostgreSQL: `DATABASE_URL=postgresql+psycopg://…` (`uv sync --extra postgres`) |
| Cache    | In-process memory cache                | Redis: `REDIS_URL=redis://localhost:6379/0` (`uv sync --extra redis`) |
| Media    | Local folder `backend/media/`, served at `/media` | `MEDIA_DIR=/some/path`             |
| Auth     | JWT (HS256), bcrypt password hashes    | `SECRET_KEY=…` (otherwise one is generated into `backend/.secret_key`) |
| Frontend | Vanilla JS single-page app served by FastAPI (no build step) |                    |

## Architecture

```mermaid
flowchart TB
    Browser["Browser<br/>SPA: index.html + app.js<br/>(hash routes, JWT in localStorage)"]

    subgraph Server["uv run main.py — Uvicorn + FastAPI on localhost:8000"]
        direction TB
        Static["Static file mounts<br/>/ · /static/* · /media/*"]
        subgraph API["API routers /api/*"]
            direction LR
            RAuth["auth<br/>register · login"]
            RUsers["users<br/>profiles · follow"]
            RPosts["posts<br/>post · reply · repost · like"]
            RFeed["feed<br/>chronological · ranked"]
            RMedia["media<br/>image upload"]
        end
        Core["security.py — bcrypt + JWT bearer auth<br/>serializers.py — batched per-viewer flags"]
    end

    subgraph Local["Local storage (no cloud services)"]
        direction LR
        DB[("SQLite · lifefeed.db<br/>or Postgres via DATABASE_URL")]
        Cache[("In-memory cache<br/>or Redis via REDIS_URL")]
        Media[("backend/media/<br/>uploaded images")]
    end

    Browser -- "fetch /api/* with Bearer JWT" --> API
    Browser -- "page, JS/CSS, images" --> Static
    API --> Core
    API -- SQLAlchemy --> DB
    RFeed -- "ranked post ids, 60s TTL" --> Cache
    RMedia -- "write file" --> Media
    Static -- "serve /media/*" --> Media
```

### Data model

```mermaid
erDiagram
    USER ||--o{ POST : writes
    USER ||--o{ LIKE : gives
    POST ||--o{ LIKE : receives
    USER ||--o{ FOLLOW : "follows (follower)"
    USER ||--o{ FOLLOW : "is followed (followee)"
    POST |o--o{ POST : "reply_to"
    POST |o--o{ POST : "repost_of"

    USER {
        int id PK
        string username UK
        string display_name
        string bio
        string avatar_url
        string password_hash
        datetime created_at
    }
    POST {
        int id PK
        int author_id FK
        text content
        string media_url
        int reply_to_id FK "set for replies"
        int repost_of_id FK "set for reposts (no content)"
        int like_count
        int reply_count
        int repost_count
        datetime created_at
    }
    FOLLOW {
        int follower_id PK
        int followee_id PK
        datetime created_at
    }
    LIKE {
        int user_id PK
        int post_id PK
        datetime created_at
    }
```

A **reply** is a post with `reply_to_id` set. A **repost** is a post with `repost_of_id` set and no content, so reposts appear in timelines alongside regular posts. Likes, replies and reposts aimed at a repost go to the original post. Counters are denormalized onto `posts` and updated in the same transaction as the action. Deleting a post also deletes its replies, reposts and likes, through database `ON DELETE CASCADE`.

### How the feeds work

```mermaid
flowchart TD
    Req["GET /api/feed?mode=…&cursor=…"] --> Mode{mode}
    Mode -- chronological --> Chrono["Posts + reposts by you and people you follow<br/>(replies excluded), ORDER BY id DESC<br/>keyset cursor = last id seen"]
    Mode -- ranked --> Hit{"cache hit?<br/>feed:ranked:{user_id}"}
    Hit -- yes --> Page["slice ids at offset cursor"]
    Hit -- no --> Cand["Candidates: same set as chronological,<br/>last 7 days, up to 500"]
    Cand --> Score["score = (1 + likes + 2·reposts + replies) / (age_h + 2)^1.5<br/>dedupe: one entry per original post"]
    Score --> Store["cache ordered ids for 60s"] --> Page
    Chrono --> Out["serialize: author, repost_of,<br/>liked_by_me / reposted_by_me (batched)"]
    Page --> Out
```

The ranked order is cached, so scrolling through pages stays consistent. Posting, reposting, following and unfollowing clear your cached copy. Posts from other people show up after the 60s TTL expires.

## API overview

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/register`, `/api/auth/login` | returns `{access_token, user}` |
| GET | `/api/auth/me` | current user |
| GET | `/api/feed?mode=chronological\|ranked&cursor=` | home feed (auth) |
| GET/POST | `/api/posts` | explore (everyone's latest) / create post or reply |
| GET/DELETE | `/api/posts/{id}` | read / delete your own |
| GET | `/api/posts/{id}/replies`, `/api/posts/{id}/thread` | direct replies / ancestor chain |
| POST/DELETE | `/api/posts/{id}/like`, `/api/posts/{id}/repost` | idempotent toggles |
| GET/PATCH | `/api/users/{username}`, `/api/users/me` | profile / edit your profile |
| POST/DELETE | `/api/users/{username}/follow` | follow / unfollow |
| GET | `/api/users/{username}/posts?replies=`, `/likes`, `/followers`, `/following` | paginated |
| GET | `/api/users?q=`, `/api/users/suggestions` | search / who to follow |
| POST | `/api/media` | multipart image upload (JPEG/PNG/GIF/WebP, ≤5 MB) |

## Project layout

```
backend/
  main.py              entry point (uvicorn)
  app/
    main.py            FastAPI app, routers, static + media mounts
    config.py          env-driven settings with local defaults
    db.py, models.py   SQLAlchemy engine + tables
    security.py        password hashing, JWT, auth dependencies
    cache.py           in-memory / Redis cache
    storage.py         local media storage + validation
    serializers.py     Post → JSON with per-viewer flags
    routers/           auth, users, posts, feed, media
    seed.py            demo data
    static/            the web client (index.html, app.js, style.css)
  tests/               pytest API tests
```
