"""Brand router — per-user brand profile CRUD (multiple brands per user).

Convention mirrors `credits.py` / `assets.py`:
- `_ok()` / `_err()` response helpers
- `get_current_user` for auth
"""
import json
from typing import Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, UploadFile, File, Form
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.dependencies.auth import get_current_user
from src.models.accounts import User
from src.models.brand import BrandProfile
from src.models.assets import Asset
from src.schemas.brand import BrandProfileCreate, BrandProfileUpdate

router = APIRouter(prefix="/api/brand", tags=["brand"])


# Logo upload constraints: PNG only, max 5 MB.
LOGO_MAX_BYTES = 5 * 1024 * 1024
LOGO_ALLOWED_MIME = {"image/png"}
LOGO_ALLOWED_EXT = {".png"}


# ── helpers ──────────────────────────────────────────────────────────

def _ok(data: Any = None, message: str = "OK", http: int = 200):
    payload: dict[str, Any] = {"success": True, "message": message}
    if data is not None:
        payload["data"] = data
    return payload


def _err(message: str, errors: Any = None, http: int = 400):
    return {"success": False, "message": message, "errors": errors or {}}, http


def _profile_to_dict(p: BrandProfile, logo_url: str | None = None) -> dict:
    return {
        "id": p.id,
        "user_id": p.user_id,
        "brand_name": p.brand_name,
        "industry": p.industry,
        "website_url": p.website_url,
        "tone": p.tone,
        "target_audience": p.target_audience,
        "brand_summary": p.brand_summary,
        "brand_keywords": p.brand_keywords or [],
        "primary_colors": p.primary_colors or [],
        "fonts": p.fonts or [],
        "logo_asset_id": p.logo_asset_id,
        "logo_url": logo_url,
        "hashtag_pool": p.hashtag_pool or [],
        "bio": p.bio,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


async def _resolve_logo(p: BrandProfile, db: AsyncSession) -> str | None:
    """Return the public URL of the linked logo asset, if any."""
    if not p.logo_asset_id:
        return None
    result = await db.execute(
        select(Asset).where(Asset.id == p.logo_asset_id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        return None
    return asset.public_url()


async def _fetch_owned(brand_id: int, user_id: int, db: AsyncSession) -> BrandProfile | None:
    result = await db.execute(
        select(BrandProfile).where(BrandProfile.id == brand_id, BrandProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _validate_logo_asset_id(asset_id: int, user_id: int, db: AsyncSession) -> str | None:
    """Return an error message if the asset_id is invalid, else None.

    Also enforces that the linked asset is a PNG under 5 MB.
    """
    asset = (await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id)
    )).scalar_one_or_none()
    if not asset:
        return "logo_asset_id does not belong to you"
    # Must be a PNG image.
    mt = (asset.mime_type or "").lower()
    name = (asset.file or "").lower()
    if mt not in LOGO_ALLOWED_MIME and not any(name.endswith(e) for e in LOGO_ALLOWED_EXT):
        return "Logo must be a PNG image"
    # Must be under 5 MB.
    if asset.file_size and asset.file_size > LOGO_MAX_BYTES:
        return f"Logo must be under {LOGO_MAX_BYTES // (1024 * 1024)} MB"
    return None


async def _save_logo_file(
    logo: UploadFile, user_id: int, db: AsyncSession
) -> tuple[Asset, str] | tuple[None, str]:
    """Validate + save a PNG logo (≤ 5 MB) as an Asset.

    Returns (asset, "") on success or (None, error_message) on failure.
    """
    mt = (logo.content_type or "").lower()
    name = (logo.filename or "").lower()
    if mt not in LOGO_ALLOWED_MIME and not any(name.endswith(e) for e in LOGO_ALLOWED_EXT):
        return None, "Logo must be a PNG image"

    contents = await logo.read()
    if not contents:
        return None, "Logo file is empty"
    if len(contents) > LOGO_MAX_BYTES:
        return None, f"Logo must be under {LOGO_MAX_BYTES // (1024 * 1024)} MB"

    asset = Asset(
        user_id=user_id,
        name=(logo.filename or "logo.png")[:255],
        description="Brand logo",
        asset_type="image",
        mime_type=logo.content_type or "image/png",
        file_size=len(contents),
        source="uploaded",
    )
    db.add(asset)
    await db.flush()

    rel_path = f"assets/{user_id}/{asset.id}-{int(datetime.now(timezone.utc).timestamp())}.png"
    full_path = settings.MEDIA_DIR / rel_path
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(contents)
    except Exception as e:
        await db.delete(asset)
        await db.flush()
        return None, f"Failed to store logo: {e}"

    asset.file = rel_path
    await db.flush()
    await db.refresh(asset)
    return asset, ""


# ── List (paginated + filtered) ──────────────────────────────────────

@router.get("")
@router.get("/")
async def list_brands(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    search: str | None = Query(None, description="Search brand_name / industry / bio"),
    industry: str | None = Query(None, description="Filter by industry"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's brand profiles with pagination + filters."""
    base = select(BrandProfile).where(BrandProfile.user_id == user.id)
    count_base = select(BrandProfile.id).where(BrandProfile.user_id == user.id)

    if industry:
        base = base.where(BrandProfile.industry == industry)
        count_base = count_base.where(BrandProfile.industry == industry)

    if search:
        pattern = f"%{search}%"
        base = base.where(
            or_(
                BrandProfile.brand_name.ilike(pattern),
                BrandProfile.industry.ilike(pattern),
                BrandProfile.bio.ilike(pattern),
            )
        )
        count_base = count_base.where(
            or_(
                BrandProfile.brand_name.ilike(pattern),
                BrandProfile.industry.ilike(pattern),
                BrandProfile.bio.ilike(pattern),
            )
        )

    total = (
        await db.execute(select(func.count()).select_from(count_base.subquery()))
    ).scalar_one()

    rows_q = base.order_by(BrandProfile.id.desc()).offset((page - 1) * page_size).limit(page_size)
    profiles = (await db.execute(rows_q)).scalars().all()

    items = []
    for p in profiles:
        logo_url = await _resolve_logo(p, db)
        items.append(_profile_to_dict(p, logo_url))

    return _ok(
        {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size,
                "has_next": page * page_size < total,
                "has_prev": page > 1,
            },
        },
        message="Brand profiles fetched successfully",
    )


# ── CRUD ─────────────────────────────────────────────────────────────

@router.post("")
@router.post("/")
async def create_brand(
    payload: BrandProfileCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a brand profile for the current user."""
    if payload.logo_asset_id:
        err = await _validate_logo_asset_id(payload.logo_asset_id, user.id, db)
        if err:
            return _err(err, http=422)

    profile = BrandProfile(
        user_id=user.id,
        brand_name=payload.brand_name,
        industry=payload.industry,
        website_url=payload.website_url,
        tone=payload.tone,
        target_audience=payload.target_audience,
        brand_summary=payload.brand_summary,
        brand_keywords=payload.brand_keywords,
        primary_colors=payload.primary_colors,
        fonts=payload.fonts,
        logo_asset_id=payload.logo_asset_id,
        hashtag_pool=payload.hashtag_pool,
        bio=payload.bio,
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    logo_url = await _resolve_logo(profile, db)
    return _ok(_profile_to_dict(profile, logo_url), message="Brand profile created", http=201), 201


# ── Create with logo upload (multipart) ─────────────────────────────

@router.post("/create-with-logo")
@router.post("/create-with-logo/")
async def create_brand_with_logo(
    logo: UploadFile = File(...),
    brand_name: str = Form(""),
    industry: str = Form(""),
    website_url: str = Form(""),
    tone: str = Form(""),
    target_audience: str = Form(""),
    brand_summary: str = Form(""),
    brand_keywords: str = Form(""),  # comma-separated
    primary_colors: str = Form(""),  # comma-separated hex
    fonts: str = Form(""),  # comma-separated
    hashtag_pool: str = Form(""),  # comma-separated
    bio: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a brand profile AND upload a PNG logo (≤ 5 MB) in one request.

    Each field is sent as its own form field (multipart/form-data).
    `brand_keywords`, `primary_colors`, `fonts`, `hashtag_pool` are
    comma-separated strings.
    """
    # Save the logo first.
    asset, err = await _save_logo_file(logo, user.id, db)
    if err:
        return _err(err, http=422)

    def _split_list(s: str) -> list[str]:
        return [x.strip() for x in s.split(",") if x.strip()] if s else []

    profile = BrandProfile(
        user_id=user.id,
        brand_name=brand_name,
        industry=industry,
        website_url=website_url,
        tone=tone,
        target_audience=target_audience,
        brand_summary=brand_summary,
        brand_keywords=_split_list(brand_keywords),
        primary_colors=_split_list(primary_colors),
        fonts=_split_list(fonts),
        logo_asset_id=asset.id,
        hashtag_pool=_split_list(hashtag_pool),
        bio=bio,
    )
    db.add(profile)
    await db.flush()
    await db.refresh(profile)
    logo_url = await _resolve_logo(profile, db)
    return _ok(_profile_to_dict(profile, logo_url), message="Brand profile created with logo", http=201), 201


@router.get("/{brand_id}")
async def get_brand(
    brand_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single brand profile owned by the current user."""
    profile = await _fetch_owned(brand_id, user.id, db)
    if not profile:
        return _err("Brand profile not found", http=404)
    logo_url = await _resolve_logo(profile, db)
    return _ok(_profile_to_dict(profile, logo_url), message="Brand profile fetched")


@router.put("/{brand_id}")
async def update_brand(
    brand_id: int,
    payload: BrandProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a brand profile owned by the current user (partial update)."""
    profile = await _fetch_owned(brand_id, user.id, db)
    if not profile:
        return _err("Brand profile not found", http=404)

    data = payload.model_dump(exclude_unset=True)

    if "logo_asset_id" in data and data["logo_asset_id"]:
        err = await _validate_logo_asset_id(data["logo_asset_id"], user.id, db)
        if err:
            return _err(err, http=422)

    for k, v in data.items():
        setattr(profile, k, v)
    await db.flush()
    await db.refresh(profile)
    logo_url = await _resolve_logo(profile, db)
    return _ok(_profile_to_dict(profile, logo_url), message="Brand profile updated")


# ── Update with logo upload (multipart) ──────────────────────────────

@router.put("/{brand_id}/update-with-logo")
@router.put("/{brand_id}/update-with-logo/")
async def update_brand_with_logo(
    brand_id: int,
    logo: UploadFile = File(...),
    brand_name: str = Form(None),
    industry: str = Form(None),
    website_url: str = Form(None),
    tone: str = Form(None),
    target_audience: str = Form(None),
    brand_summary: str = Form(None),
    brand_keywords: str = Form(None),  # comma-separated
    primary_colors: str = Form(None),  # comma-separated hex
    fonts: str = Form(None),  # comma-separated
    hashtag_pool: str = Form(None),  # comma-separated
    bio: str = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a brand profile AND upload a new PNG logo (≤ 5 MB) in one request.

    Each field is sent as its own form field (multipart/form-data).
    Only the fields you send are updated; omitted fields are left as-is.
    `brand_keywords`, `primary_colors`, `fonts`, `hashtag_pool` are
    comma-separated strings.
    """
    profile = await _fetch_owned(brand_id, user.id, db)
    if not profile:
        return _err("Brand profile not found", http=404)

    # Save the new logo first.
    asset, err = await _save_logo_file(logo, user.id, db)
    if err:
        return _err(err, http=422)

    def _split_list(s: str | None) -> list[str] | None:
        if s is None:
            return None
        return [x.strip() for x in s.split(",") if x.strip()]

    # Apply field updates (only non-None values).
    field_map = {
        "brand_name": brand_name,
        "industry": industry,
        "website_url": website_url,
        "tone": tone,
        "target_audience": target_audience,
        "brand_summary": brand_summary,
        "brand_keywords": _split_list(brand_keywords),
        "primary_colors": _split_list(primary_colors),
        "fonts": _split_list(fonts),
        "hashtag_pool": _split_list(hashtag_pool),
        "bio": bio,
    }
    for k, v in field_map.items():
        if v is not None:
            setattr(profile, k, v)

    profile.logo_asset_id = asset.id
    await db.flush()
    await db.refresh(profile)
    logo_url = await _resolve_logo(profile, db)
    return _ok(_profile_to_dict(profile, logo_url), message="Brand profile updated with logo")


@router.delete("/{brand_id}")
async def delete_brand(
    brand_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a brand profile owned by the current user."""
    profile = await _fetch_owned(brand_id, user.id, db)
    if not profile:
        return _err("Brand profile not found", http=404)
    await db.delete(profile)
    await db.flush()
    return _ok(message="Brand profile deleted")


# ── Logo upload only (PNG, ≤ 5 MB) ───────────────────────────────────

@router.post("/{brand_id}/logo")
async def upload_brand_logo(
    brand_id: int,
    logo: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PNG logo (≤ 5 MB) for an existing brand profile."""
    profile = await _fetch_owned(brand_id, user.id, db)
    if not profile:
        return _err("Brand profile not found", http=404)

    asset, err = await _save_logo_file(logo, user.id, db)
    if err:
        return _err(err, http=422)

    profile.logo_asset_id = asset.id
    await db.flush()
    await db.refresh(profile)
    logo_url = await _resolve_logo(profile, db)
    return _ok(
        {"brand_id": profile.id, "logo_asset_id": asset.id, "logo_url": logo_url},
        message="Logo uploaded",
        http=201,
    ), 201
