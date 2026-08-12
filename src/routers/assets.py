"""Assets router — per-user media asset management.

Metadata (name/type/tags/...) lives in the DB; the binary is stored on
disk under `media/assets/<user_id>/...` and referenced by a relative
`file` path (same convention as PostMedia / content_plans). External
URLs are also supported for assets hosted elsewhere.

Convention mirrors `credits.py` / `content_plans.py`:
- `_ok()` / `_err()` response helpers
- `get_current_user` for auth (every asset is scoped to the current user)
"""
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.dependencies.auth import get_current_user
from src.models.accounts import User
from src.models.assets import Asset, ASSET_TYPES, ASSET_SOURCES, EXT_BY_TYPE
from src.models.posts import Post
from src.models.post_media import PostMedia
from src.schemas.assets import (
    AssetCreate, AssetUpdate, AssetOut, AssetListOut, AssetSummary,
)

router = APIRouter(prefix="/api/assets", tags=["assets"])


# Max upload size per file: 15 MB for both images and videos.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_VIDEO_UPLOAD_BYTES = 15 * 1024 * 1024

# Per-user total storage limit (500 MB) shared across all asset types.
USER_STORAGE_LIMIT_BYTES = 500 * 1024 * 1024

# Only PNG / JPEG images are allowed for uploads.
ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg"}
ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg"}

# Allow common short-form / reel video uploads.
ALLOWED_VIDEO_MIME = {
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
    "video/mpeg",
}
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".avi", ".webm", ".m4v", ".mpeg", ".mpg"}

router = APIRouter(prefix="/api/assets", tags=["assets"])


# ── helpers ──────────────────────────────────────────────────────────

def _ok(data: Any = None, message: str = "OK", http: int = 200):
    payload: dict[str, Any] = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


def _err(message: str, errors: Any = None, http: int = 400):
    return {"success": False, "message": message, "errors": errors or {}}, http


def _asset_to_dict(a: Asset) -> dict:
    return {
        "id": a.id,
        "user_id": a.user_id,
        "name": a.name,
        "description": a.description or "",
        "asset_type": a.asset_type,
        "file": a.file,
        "url": a.url,
        "public_url": a.public_url(),
        "thumbnail_url": a.thumbnail_url,
        "mime_type": a.mime_type,
        "file_size": a.file_size,
        "source": a.source,
        "external_id": a.external_id,
        "tags": a.tags or [],
        "meta": a.meta or {},
        "is_favorite": a.is_favorite,
        "is_archived": a.is_archived,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }


# ── List + summary ───────────────────────────────────────────────────

@router.get("")
@router.get("/")
async def list_assets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    asset_type: str | None = Query(None, description=f"Filter by type: {', '.join(ASSET_TYPES)}"),
    search: str | None = Query(None, description="Search name/description"),
    tag: str | None = Query(None, description="Filter by tag"),
    source: str | None = Query(None, description="Filter by source"),
    favorite: bool | None = Query(None, description="Only favorites"),
    archived: bool | None = Query(None, description="Only archived (default: hidden)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's assets with pagination + filters."""
    base = select(Asset).where(Asset.user_id == user.id)
    count_base = select(Asset.id).where(Asset.user_id == user.id)

    # By default hide archived items unless explicitly requested.
    if archived is None:
        base = base.where(Asset.is_archived.is_(False))
        count_base = count_base.where(Asset.is_archived.is_(False))
    elif archived:
        base = base.where(Asset.is_archived.is_(True))
        count_base = count_base.where(Asset.is_archived.is_(True))

    if asset_type:
        if asset_type not in ASSET_TYPES:
            return _err(
                f"Invalid asset_type. Allowed: {', '.join(ASSET_TYPES)}",
                http=422,
            )
        base = base.where(Asset.asset_type == asset_type)
        count_base = count_base.where(Asset.asset_type == asset_type)

    if source:
        base = base.where(Asset.source == source)
        count_base = count_base.where(Asset.source == source)

    if favorite:
        base = base.where(Asset.is_favorite.is_(True))
        count_base = count_base.where(Asset.is_favorite.is_(True))

    if tag:
        # JSON column — match the tag substring against the JSON text.
        # Good enough for filtering; for large datasets a GIN index +
        # jsonb containment (tags ? :tag) would be more efficient.
        tag_pat = f'%"{tag}"%'
        base = base.where(Asset.tags.cast(str).ilike(tag_pat))
        count_base = count_base.where(Asset.tags.cast(str).ilike(tag_pat))

    if search:
        pattern = f"%{search}%"
        base = base.where(
            or_(Asset.name.ilike(pattern), Asset.description.ilike(pattern))
        )
        count_base = count_base.where(
            or_(Asset.name.ilike(pattern), Asset.description.ilike(pattern))
        )

    total = (
        await db.execute(select(func.count()).select_from(count_base.subquery()))
    ).scalar_one()

    rows_q = base.order_by(Asset.id.desc()).offset((page - 1) * page_size).limit(page_size)
    assets = (await db.execute(rows_q)).scalars().all()

    return _ok(
        {
            "items": [_asset_to_dict(a) for a in assets],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
                "has_next": page * page_size < total,
                "has_prev": page > 1,
            },
        },
        message="Assets fetched successfully",
    )


@router.get("/summary")
async def assets_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate counts for the current user's asset library."""
    total = (
        await db.execute(
            select(func.count(Asset.id)).where(
                Asset.user_id == user.id, Asset.is_archived.is_(False)
            )
        )
    ).scalar_one()

    by_type_rows = (
        await db.execute(
            select(Asset.asset_type, func.count(Asset.id))
            .where(Asset.user_id == user.id, Asset.is_archived.is_(False))
            .group_by(Asset.asset_type)
        )
    ).all()
    by_type = {row[0]: row[1] for row in by_type_rows}

    # Breakdown by source (uploaded / ai).
    by_source_rows = (
        await db.execute(
            select(Asset.source, func.count(Asset.id))
            .where(Asset.user_id == user.id, Asset.is_archived.is_(False))
            .group_by(Asset.source)
        )
    ).all()
    by_source = {row[0]: row[1] for row in by_source_rows}

    # Count of AI-generated assets (source="ai").
    ai_generated = by_source.get("ai", 0)

    favorites = (
        await db.execute(
            select(func.count(Asset.id)).where(
                Asset.user_id == user.id,
                Asset.is_favorite.is_(True),
                Asset.is_archived.is_(False),
            )
        )
    ).scalar_one()

    archived = (
        await db.execute(
            select(func.count(Asset.id)).where(
                Asset.user_id == user.id, Asset.is_archived.is_(True)
            )
        )
    ).scalar_one()

    # Total storage used by this user (sum of file_size across all assets).
    total_size = (
        await db.execute(
            select(func.coalesce(func.sum(Asset.file_size), 0))
            .where(Asset.user_id == user.id)
        )
    ).scalar_one()

    return _ok(
        {
            "total": total,
            "by_type": by_type,
            "by_source": by_source,
            "ai_generated": ai_generated,
            "favorites": favorites,
            "archived": archived,
            "total_size": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "total_size_kb": round(total_size / 1024, 2),
            "storage_limit": USER_STORAGE_LIMIT_BYTES,
            "storage_limit_mb": USER_STORAGE_LIMIT_BYTES // (1024 * 1024),
            "storage_limit_kb": USER_STORAGE_LIMIT_BYTES // 1024,
            "remaining": max(USER_STORAGE_LIMIT_BYTES - total_size, 0),
            "remaining_mb": round(max(USER_STORAGE_LIMIT_BYTES - total_size, 0) / (1024 * 1024), 2),
            "remaining_kb": round(max(USER_STORAGE_LIMIT_BYTES - total_size, 0) / 1024, 2),
        },
        message="Asset summary",
    )


# ── CRUD ─────────────────────────────────────────────────────────────

@router.post("")
@router.post("/")
async def create_asset(
    payload: AssetCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new asset metadata record for the current user.

    Allowed `source` values: `uploaded` or `ai`. For file uploads use
    `POST /api/assets/upload` instead.
    """
    if payload.asset_type not in ASSET_TYPES:
        return _err(
            f"Invalid asset_type. Allowed: {', '.join(ASSET_TYPES)}",
            http=422,
        )
    if payload.source not in ASSET_SOURCES:
        return _err(
            f"Invalid source. Allowed: {', '.join(ASSET_SOURCES)}",
            http=422,
        )

    asset = Asset(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        asset_type=payload.asset_type,
        url=payload.url,
        thumbnail_url=payload.thumbnail_url,
        mime_type=payload.mime_type,
        file_size=payload.file_size,
        source=payload.source,
        external_id=payload.external_id,
        tags=payload.tags,
        meta=payload.meta,
        is_favorite=payload.is_favorite,
        is_archived=payload.is_archived,
    )
    db.add(asset)
    await db.flush()
    await db.refresh(asset)
    return _ok(_asset_to_dict(asset), message="Asset created", http=201), 201


def _is_allowed_image(upload: UploadFile) -> bool:
    """True if the file is a PNG or JPEG (by mime or extension)."""
    mt = (upload.content_type or "").lower()
    name = (upload.filename or "").lower()
    return mt in ALLOWED_IMAGE_MIME or any(name.endswith(e) for e in ALLOWED_IMAGE_EXT)


def _is_allowed_video(upload: UploadFile) -> bool:
    """True if the file is a supported video (by mime or extension)."""
    mt = (upload.content_type or "").lower()
    name = (upload.filename or "").lower()
    return mt in ALLOWED_VIDEO_MIME or any(name.endswith(e) for e in ALLOWED_VIDEO_EXT)


def _ext_for_image(filename: str | None) -> str:
    """Choose a safe extension for an uploaded image."""
    if filename:
        _, dot, ext = filename.rpartition(".")
        if dot and ext.lower() in {"png", "jpg", "jpeg"}:
            return f".{ext.lower()}"
    return ".png"


def _ext_for_video(filename: str | None) -> str:
    """Choose a safe extension for an uploaded video."""
    if filename:
        _, dot, ext = filename.rpartition(".")
        if dot and ext.lower() in {"mp4", "mov", "avi", "webm", "m4v", "mpeg", "mpg"}:
            return f".{ext.lower()}"
    return ".mp4"


@router.post("/upload")
async def upload_assets(
    files: List[UploadFile] = File(...),
    name: str = Form(None),
    description: str = Form(""),
    tags: str = Form(""),  # comma-separated
    is_favorite: bool = Form(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload one or more image files and create an asset per file.

    Rules:
      - Only PNG / JPEG images are accepted (image/png, image/jpeg).
      - Max 10 MB per file.
      - Multiple files may be sent in a single request.

    The shared form metadata (`description`, `tags`, `is_favorite`) is
    applied to every asset. `name` is used as-is when a single file is
    sent; for multiple files the filename is used (ignoring `name`).
    The binary is saved under `media/assets/<user_id>/<asset_id>-<ts><ext>`.
    """
    if not files:
        return _err("No files provided", http=422)

    # Per-user storage quota: sum of all file_size values across images + videos
    # must stay under USER_STORAGE_LIMIT_BYTES (500 MB). We check the current
    # usage once before processing the batch.
    current_usage = (
        await db.execute(
            select(func.coalesce(func.sum(Asset.file_size), 0))
            .where(Asset.user_id == user.id)
        )
    ).scalar_one()
    if current_usage >= USER_STORAGE_LIMIT_BYTES:
        return _err(
            f"Storage limit reached ({USER_STORAGE_LIMIT_BYTES // (1024 * 1024)} MB). "
            f"Delete some assets to free up space.",
            http=413,
        )

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    use_form_name = name and len(files) == 1

    created: list[dict] = []
    errors: list[dict] = []

    for idx, upload in enumerate(files):
        # Validate type.
        if not _is_allowed_image(upload):
            errors.append({
                "index": idx,
                "filename": upload.filename,
                "error": "Only PNG / JPEG images are allowed",
            })
            continue

        contents = await upload.read()
        if not contents:
            errors.append({
                "index": idx,
                "filename": upload.filename,
                "error": "File is empty",
            })
            continue
        if len(contents) > MAX_UPLOAD_BYTES:
            errors.append({
                "index": idx,
                "filename": upload.filename,
                "error": f"File too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
            })
            continue

        # Check the per-user 500 MB quota for this individual file.
        if current_usage + len(contents) > USER_STORAGE_LIMIT_BYTES:
            errors.append({
                "index": idx,
                "filename": upload.filename,
                "error": (
                    f"Upload would exceed storage limit "
                    f"({USER_STORAGE_LIMIT_BYTES // (1024 * 1024)} MB)"
                ),
            })
            continue
        current_usage += len(contents)

        resolved_name = (name if use_form_name else "").strip() or (upload.filename or "image")

        asset = Asset(
            user_id=user.id,
            name=resolved_name[:255],
            description=description or "",
            asset_type="image",
            mime_type=upload.content_type or "image/png",
            file_size=len(contents),
            source="uploaded",
            tags=tag_list,
            is_favorite=is_favorite,
        )
        db.add(asset)
        await db.flush()  # get asset.id

        ext = _ext_for_image(upload.filename)
        rel_path = f"assets/{user.id}/{asset.id}-{int(datetime.now(timezone.utc).timestamp())}{ext}"
        full_path = settings.MEDIA_DIR / rel_path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(contents)
        except Exception as e:
            await db.delete(asset)
            await db.flush()
            errors.append({
                "index": idx,
                "filename": upload.filename,
                "error": f"Failed to store file: {e}",
            })
            continue

        asset.file = rel_path
        await db.flush()
        await db.refresh(asset)
        created.append(_asset_to_dict(asset))

    if not created and errors:
        # Every file failed — return 422 with the per-file errors.
        return _err("All files rejected", errors=errors, http=422)

    return _ok(
        {"assets": created, "errors": errors, "count": len(created)},
        message=f"{len(created)} asset(s) uploaded",
        http=201,
    ), 201


@router.post("/upload-video")
@router.post("/upload/video")
async def upload_video_assets(
    files: List[UploadFile] = File(...),
    name: str = Form(None),
    description: str = Form(""),
    tags: str = Form(""),
    is_favorite: bool = Form(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload one or more video / reel files and create an asset record per file.

    Accepted formats: mp4, mov, avi, webm, m4v, mpg, mpeg.
    Max size per file: 100 MB.
    """
    if not files:
        return _err("No files provided", http=422)

    current_usage = (
        await db.execute(
            select(func.coalesce(func.sum(Asset.file_size), 0))
            .where(Asset.user_id == user.id)
        )
    ).scalar_one()
    if current_usage >= USER_STORAGE_LIMIT_BYTES:
        return _err(
            f"Storage limit reached ({USER_STORAGE_LIMIT_BYTES // (1024 * 1024)} MB). "
            f"Delete some assets to free up space.",
            http=413,
        )

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    use_form_name = name and len(files) == 1

    created: list[dict] = []
    errors: list[dict] = []

    for idx, upload in enumerate(files):
        if not _is_allowed_video(upload):
            errors.append({
                "index": idx,
                "filename": upload.filename,
                "error": "Only video files are allowed (mp4, mov, avi, webm, m4v, mpg, mpeg)",
            })
            continue

        contents = await upload.read()
        if not contents:
            errors.append({
                "index": idx,
                "filename": upload.filename,
                "error": "File is empty",
            })
            continue
        if len(contents) > MAX_VIDEO_UPLOAD_BYTES:
            errors.append({
                "index": idx,
                "filename": upload.filename,
                "error": f"Video too large (max {MAX_VIDEO_UPLOAD_BYTES // (1024 * 1024)} MB)",
            })
            continue

        if current_usage + len(contents) > USER_STORAGE_LIMIT_BYTES:
            errors.append({
                "index": idx,
                "filename": upload.filename,
                "error": (
                    f"Upload would exceed storage limit "
                    f"({USER_STORAGE_LIMIT_BYTES // (1024 * 1024)} MB)"
                ),
            })
            continue
        current_usage += len(contents)

        resolved_name = (name if use_form_name else "").strip() or (upload.filename or "video")

        asset = Asset(
            user_id=user.id,
            name=resolved_name[:255],
            description=description or "",
            asset_type="video",
            mime_type=upload.content_type or "video/mp4",
            file_size=len(contents),
            source="uploaded",
            tags=tag_list,
            is_favorite=is_favorite,
        )
        db.add(asset)
        await db.flush()

        ext = _ext_for_video(upload.filename)
        rel_path = f"assets/{user.id}/{asset.id}-{int(datetime.now(timezone.utc).timestamp())}{ext}"
        full_path = settings.MEDIA_DIR / rel_path
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_bytes(contents)
        except Exception as e:
            await db.delete(asset)
            await db.flush()
            errors.append({
                "index": idx,
                "filename": upload.filename,
                "error": f"Failed to store file: {e}",
            })
            continue

        asset.file = rel_path
        await db.flush()
        await db.refresh(asset)
        created.append(_asset_to_dict(asset))

    if not created and errors:
        return _err("All video files rejected", errors=errors, http=422)

    return _ok(
        {"assets": created, "errors": errors, "count": len(created)},
        message=f"{len(created)} video asset(s) uploaded",
        http=201,
    ), 201


async def _fetch_owned(asset_id: int, user_id: int, db: AsyncSession) -> Asset | None:
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id)
    )
    return result.scalar_one_or_none()


@router.get("/{asset_id}")
async def get_asset(
    asset_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single asset owned by the current user."""
    asset = await _fetch_owned(asset_id, user.id, db)
    if not asset:
        return _err("Asset not found", http=404)
    return _ok(_asset_to_dict(asset), message="Asset fetched")


@router.put("/{asset_id}")
async def update_asset(
    asset_id: int,
    payload: AssetUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an asset's metadata (partial update)."""
    asset = await _fetch_owned(asset_id, user.id, db)
    if not asset:
        return _err("Asset not found", http=404)

    if payload.asset_type is not None and payload.asset_type not in ASSET_TYPES:
        return _err(
            f"Invalid asset_type. Allowed: {', '.join(ASSET_TYPES)}",
            http=422,
        )
    if payload.source is not None and payload.source not in ASSET_SOURCES:
        return _err(
            f"Invalid source. Allowed: {', '.join(ASSET_SOURCES)}",
            http=422,
        )

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(asset, k, v)
    await db.flush()
    await db.refresh(asset)
    return _ok(_asset_to_dict(asset), message="Asset updated")


@router.delete("/{asset_id}")
async def delete_asset(
    asset_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete an asset owned by the current user.

    Also removes the stored binary from `media/assets/` if present.
    Blocks deletion if the asset is attached to any post that is still
    pending, scheduled, or processing (i.e. not yet posted/failed).
    """
    asset = await _fetch_owned(asset_id, user.id, db)
    if not asset:
        return _err("Asset not found", http=404)

    # Check if this asset is used by any active (not-yet-posted) post.
    target = asset.file or asset.url
    if target:
        active_statuses = [
            Post.STATUS_PENDING,
            Post.STATUS_SCHEDULED,
            Post.STATUS_PROCESSING,
        ]
        linked = (
            await db.execute(
                select(Post.id, Post.platform, Post.status, Post.scheduled_time)
                .join(PostMedia, PostMedia.post_id == Post.id)
                .where(
                    PostMedia.file == target,
                    Post.user_id == user.id,
                    Post.status.in_(active_statuses),
                )
                .limit(10)
            )
        ).all()
        if linked:
            posts_info = [
                {
                    "post_id": r[0],
                    "platform": r[1],
                    "status": r[2],
                    "scheduled_time": r[3].isoformat() if r[3] else None,
                }
                for r in linked
            ]
            return _err(
                "This asset is used in a pending/scheduled post and cannot be deleted. "
                "Remove it from those posts first.",
                errors={"linked_posts": posts_info},
                http=409,
            )

    # Remove the binary from disk (best-effort).
    rel = asset.file
    await db.delete(asset)
    await db.flush()
    if rel:
        try:
            full = settings.MEDIA_DIR / rel
            if full.is_file():
                full.unlink()
        except Exception:
            pass
    return _ok(message="Asset deleted")


# ── Quick actions: favorite / archive ────────────────────────────────

@router.post("/{asset_id}/favorite")
async def toggle_favorite(
    asset_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle the is_favorite flag on an asset."""
    asset = await _fetch_owned(asset_id, user.id, db)
    if not asset:
        return _err("Asset not found", http=404)
    asset.is_favorite = not asset.is_favorite
    await db.flush()
    await db.refresh(asset)
    return _ok({"id": asset.id, "is_favorite": asset.is_favorite})


@router.post("/{asset_id}/unfavorite")
async def unfavorite_asset(
    asset_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an asset from favorites (sets is_favorite=False)."""
    asset = await _fetch_owned(asset_id, user.id, db)
    if not asset:
        return _err("Asset not found", http=404)
    asset.is_favorite = False
    await db.flush()
    await db.refresh(asset)
    return _ok({"id": asset.id, "is_favorite": asset.is_favorite})

