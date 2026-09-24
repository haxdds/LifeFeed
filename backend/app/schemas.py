from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

USERNAME_PATTERN = r"^[A-Za-z0-9_]{3,30}$"
MAX_POST_LENGTH = 280


class RegisterIn(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=72)
    display_name: str | None = Field(default=None, max_length=50)


class LoginIn(BaseModel):
    username: str
    password: str


class UserUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    bio: str | None = Field(default=None, max_length=160)
    avatar_url: str | None = Field(default=None, max_length=255)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    bio: str
    avatar_url: str | None
    created_at: datetime


class ProfileOut(UserOut):
    follower_count: int
    following_count: int
    post_count: int
    is_following: bool
    follows_you: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class PostIn(BaseModel):
    content: str = Field(default="", max_length=MAX_POST_LENGTH)
    media_url: str | None = Field(default=None, max_length=255)
    reply_to_id: int | None = None


class PostOut(BaseModel):
    id: int
    author: UserOut
    content: str
    media_url: str | None
    reply_to_id: int | None
    reply_to_username: str | None
    like_count: int
    reply_count: int
    repost_count: int
    created_at: datetime
    liked_by_me: bool
    reposted_by_me: bool
    repost_of: "PostOut | None" = None


class PostPage(BaseModel):
    items: list[PostOut]
    next_cursor: str | None


class UserPage(BaseModel):
    items: list[UserOut]
    next_cursor: str | None


class MediaOut(BaseModel):
    url: str
