"""Media storage on the local filesystem, served back at /media/<name>."""

import uuid

from fastapi import HTTPException, UploadFile, status

from . import config

ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

# First bytes of each allowed format, so a renamed non-image is rejected.
_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
}

MEDIA_URL_PREFIX = "/media/"


async def save_upload(file: UploadFile) -> str:
    content_type = file.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only JPEG, PNG, GIF and WebP images are allowed"
        )

    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large")
    if not data.startswith(_SIGNATURES[content_type]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File contents don't match its type")

    config.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ALLOWED_TYPES[content_type]}"
    (config.MEDIA_DIR / name).write_bytes(data)
    return MEDIA_URL_PREFIX + name


def is_local_media_url(url: str) -> bool:
    name = url.removeprefix(MEDIA_URL_PREFIX)
    return (
        url.startswith(MEDIA_URL_PREFIX)
        and "/" not in name
        and ".." not in name
        and (config.MEDIA_DIR / name).is_file()
    )
