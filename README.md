# LifeFeed

A Twitter clone built as a practice project. Core social features — posts, follows, likes, feeds — deployed on AWS.

## Stack

- **Backend**: Python (FastAPI)
- **Database**: AWS RDS (PostgreSQL)
- **Cache**: AWS ElastiCache (Redis)
- **Compute**: AWS EC2
- **Storage**: AWS S3 (media uploads)
- **Auth**: JWT

## Features

- Post, reply, repost, like
- Follow/unfollow users
- Home feed (chronological + ranked)
- User profiles
- Media uploads

## Getting Started

```bash
# Install dependencies
pip install -e .

# Run locally
python main.py
```

## Architecture

```
Client → EC2 (API) → RDS (Postgres)
                   → ElastiCache (Redis) ← feed caching, sessions
                   → S3 (media)
```
