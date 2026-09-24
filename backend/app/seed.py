"""Fill the local database with demo users and posts.

    uv run python -m app.seed          # add demo data (skips if it already exists)
    uv run python -m app.seed --reset  # wipe the database first

Every demo user's password is "password123".
"""

import argparse
import random
import struct
import uuid
import zlib
from datetime import timedelta

from sqlalchemy import select

from . import config
from .db import Base, SessionLocal, engine, init_db
from .models import Follow, Like, Post, User, utcnow
from .security import hash_password

PASSWORD = "password123"

USERS = [
    ("ada", "Ada Lovelace", "First programmer. Poetical scientist. Big fan of engines."),
    ("grace", "Grace Hopper", "Rear admiral. Compiler whisperer. It's easier to ask forgiveness."),
    ("linus", "Linus", "Just a hobby, won't be big and professional."),
    ("margaret", "Margaret Hamilton", "Software engineering, before it had a name. 🚀"),
    ("alan", "Alan Turing", "Can machines think? Asking for a friend."),
    ("katherine", "Katherine Johnson", "Trajectories, orbits, and checking the computer's math."),
]

POSTS = [
    ("ada", "Wrote some notes on the Analytical Engine today. I think it could compose music, not just crunch numbers.", 70),
    ("grace", "Found an actual moth in the relay. Taped it into the logbook. First real case of a bug being found.", 60),
    ("linus", "I'm doing a (free) operating system. Just a hobby. Anyone interested?", 52),
    ("margaret", "The 1202 alarm was the software doing exactly what it was designed to do: drop the low-priority work and keep landing.", 44),
    ("alan", "Proposal: instead of asking 'can machines think', let's play a game.", 40),
    ("katherine", "Get the girl to check the numbers. If she says they're good, I'm ready to go. — John Glenn, probably about me", 30),
    ("grace", "A ship in port is safe, but that's not what ships are built for.", 26),
    ("ada", "That brain of mine is something more than merely mortal, as time will show.", 20),
    ("linus", "Talk is cheap. Show me the code.", 16),
    ("margaret", "Looking back, we were the luckiest people in the world. There was no choice but to be pioneers.", 12),
    ("alan", "We can only see a short distance ahead, but we can see plenty there that needs to be done.", 8),
    ("katherine", "Like what you do, and then you will do your best.", 5),
    ("grace", "The most dangerous phrase in the language is: we've always done it this way.", 3),
    ("ada", "Hello LifeFeed! Everything here runs locally — SQLite, a local cache and a folder for media.", 1),
]

REPLIES = [
    (1, "grace", "@ada music from an engine? I'd like to see the compiler for that."),
    (1, "alan", "Composition is just a well-specified procedure. I'm with Ada on this one."),
    (2, "margaret", "Best log entry of all time."),
    (3, "ada", "Interested! What's the license?"),
    (4, "katherine", "And the math was right. Every time."),
    (9, "grace", "Also: show me the tests."),
]

FOLLOWS = {
    "ada": ["grace", "alan", "margaret", "katherine"],
    "grace": ["ada", "margaret", "linus"],
    "linus": ["grace", "alan"],
    "margaret": ["ada", "grace", "katherine"],
    "alan": ["ada", "grace"],
    "katherine": ["margaret", "ada", "grace"],
}


def _gradient_png(width: int = 600, height: int = 300) -> bytes:
    """A small generated PNG so the demo shows an image post without shipping binaries."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows += bytes((29 + x * 90 // width, 155 - y * 60 // height, 240 - x * 40 // width))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(rows))) + chunk(b"IEND", b"")


def seed(reset: bool = False) -> None:
    if reset:
        Base.metadata.drop_all(engine)
    init_db()

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.username == "ada")) is not None:
            print("Demo data already present. Use --reset to start over.")
            return

        rng = random.Random(42)
        now = utcnow()
        password_hash = hash_password(PASSWORD)
        users = {
            name: User(username=name, display_name=display, bio=bio, password_hash=password_hash)
            for name, display, bio in USERS
        }
        db.add_all(users.values())
        db.flush()

        for follower, followees in FOLLOWS.items():
            for followee in followees:
                db.add(Follow(follower_id=users[follower].id, followee_id=users[followee].id))

        config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        image_name = f"{uuid.uuid4().hex}.png"
        (config.MEDIA_DIR / image_name).write_bytes(_gradient_png())

        posts: list[Post] = []
        for i, (author, content, hours_ago) in enumerate(POSTS):
            post = Post(
                author_id=users[author].id,
                content=content,
                media_url=f"/media/{image_name}" if i == len(POSTS) - 1 else None,
                created_at=now - timedelta(hours=hours_ago, minutes=rng.randint(0, 50)),
            )
            db.add(post)
            posts.append(post)
        db.flush()

        for parent_index, author, content in REPLIES:
            parent = posts[parent_index - 1]
            db.add(
                Post(
                    author_id=users[author].id,
                    content=content,
                    reply_to_id=parent.id,
                    created_at=min(now, parent.created_at + timedelta(minutes=rng.randint(5, 120))),
                )
            )
            parent.reply_count += 1

        for post in posts:
            for name, user in users.items():
                if user.id == post.author_id:
                    continue
                if rng.random() < 0.45:
                    db.add(Like(user_id=user.id, post_id=post.id))
                    post.like_count += 1
                if rng.random() < 0.15:
                    db.add(
                        Post(
                            author_id=user.id,
                            repost_of_id=post.id,
                            created_at=min(now, post.created_at + timedelta(minutes=rng.randint(10, 240))),
                        )
                    )
                    post.repost_count += 1

        db.commit()
    print(f"Seeded {len(USERS)} users and {len(POSTS)} posts. Log in as any of "
          f"{', '.join(u[0] for u in USERS)} with password '{PASSWORD}'.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop all data before seeding")
    seed(reset=parser.parse_args().reset)
