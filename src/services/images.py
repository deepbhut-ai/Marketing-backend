"""
Gemini image generation — replaces apps/content_plans/services/images.py.

Decrypts the caller's stored API key and uses the google-genai SDK;
falls back to REST if the SDK isn't installed.
"""
import base64
import os
import uuid

import requests

from src.core.config import settings
from src.services.crypto import decrypt


class GeminiError(Exception):
    pass

PLATFORM_ASPECT = {
    "instagram": "1:1",
    "facebook": "1.91:1",
    "linkedin": "1.91:1",
    "x": "16:9",
}


def build_prompt(topic: str, platform: str, brand_summary: str = "", override: str = "") -> str:
    if override and override.strip():
        return override.strip()
    aspect = PLATFORM_ASPECT.get(platform, "1:1")
    brand_block = f" Brand style: {brand_summary.strip()}." if brand_summary.strip() else ""
    return (
        f"Create a {aspect} aspect ratio social media image for: {topic}."
        f"{brand_block} Bold, on-brand, high contrast, scroll-stopping. "
        "No text overlays."
    )


def _save_png(plan_id: int, item_id: int, png_bytes: bytes) -> str:
    """Save PNG to MEDIA_DIR and return the relative path."""
    dir_path = settings.MEDIA_DIR / "content_plans" / str(plan_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    name = f"{item_id}-{uuid.uuid4().hex[:8]}.png"
    full_path = dir_path / name
    full_path.write_bytes(png_bytes)
    # Return path relative to MEDIA_DIR (matches Django's default_storage behaviour)
    return f"content_plans/{plan_id}/{name}"


def _generate_via_sdk(api_key: str, model: str, prompt: str) -> bytes:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
    )
    for cand in getattr(response, "candidates", []) or []:
        content = getattr(cand, "content", None)
        for part in getattr(content, "parts", []) or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                return inline.data
    raise GeminiError("Gemini SDK returned no image data")


def _generate_via_rest(api_key: str, model: str, prompt: str) -> bytes:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    try:
        r = requests.post(url, json=payload, timeout=settings.GEMINI_REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise GeminiError(f"Gemini REST call failed: {exc}") from exc
    if r.status_code >= 400:
        raise GeminiError(f"Gemini HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    for cand in data.get("candidates", []):
        for part in (cand.get("content") or {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise GeminiError("Gemini REST returned no image data")


def generate(item, brand_summary: str = "", prompt_override: str = "") -> str:
    """Generate a Gemini image for a ContentPlanItem and save it.

    `item` is a ContentPlanItem ORM object (sync session, from Celery).
    Returns the path relative to MEDIA_ROOT.
    """
    # Lazy-load the encrypted key from the user
    from sqlalchemy.orm import Session
    from src.models.content_plans import UserAIKey

    # item is a SQLAlchemy ORM object from a sync session
    record = item.plan.user.ai_key
    if record is None or not record.gemini_key_encrypted:
        raise GeminiError("User has no Gemini key on file")
    api_key = decrypt(record.gemini_key_encrypted)

    model = (
        item.plan.image_model
        or (record.default_image_model if record else "")
        or settings.GEMINI_IMAGE_MODEL
    )
    prompt = build_prompt(item.topic, item.platform, brand_summary, prompt_override)

    try:
        png = _generate_via_sdk(api_key, model, prompt)
    except ImportError:
        png = _generate_via_rest(api_key, model, prompt)
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"Gemini generation failed: {exc}") from exc

    saved_path = _save_png(item.plan_id, item.id, png)
    item.image_prompt = prompt
    return saved_path


def _save_generated_png(png_bytes: bytes) -> str:
    """Save a standalone generated PNG. Returns path relative to MEDIA_DIR."""
    dir_path = settings.MEDIA_DIR / "generated"
    dir_path.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}.png"
    full_path = dir_path / name
    full_path.write_bytes(png_bytes)
    return f"generated/{name}"


def generate_content_image(
    api_key: str,
    text: str,
    platform: str = "instagram",
    brand_summary: str = "",
    model: str = "",
    prompt_override: str = "",
) -> dict:
    """Generate a standalone image from free-form content text.

    Returns ``{"path": str, "prompt": str}``.
    """
    model = model or settings.GEMINI_IMAGE_MODEL
    prompt = build_prompt(text, platform, brand_summary, prompt_override)
    print(f"[gemini-image] DEBUG: model={model}, platform={platform}, key_last4=...{api_key[-4:]}", flush=True)
    print(f"[gemini-image] DEBUG: prompt={prompt[:100]}...", flush=True)

    try:
        print(f"[gemini-image] DEBUG: trying SDK...", flush=True)
        png = _generate_via_sdk(api_key, model, prompt)
        print(f"[gemini-image] DEBUG: SDK returned {len(png)} bytes", flush=True)
    except ImportError:
        print(f"[gemini-image] DEBUG: SDK not available, trying REST...", flush=True)
        png = _generate_via_rest(api_key, model, prompt)
        print(f"[gemini-image] DEBUG: REST returned {len(png)} bytes", flush=True)
    except GeminiError:
        raise
    except Exception as exc:
        print(f"[gemini-image] DEBUG: SDK error: {exc}", flush=True)
        # If the model wasn't found (404), retry with the default model
        if "404" in str(exc) or "NOT_FOUND" in str(exc):
            print(f"[gemini-image] DEBUG: model not found, retrying with {settings.GEMINI_IMAGE_MODEL}", flush=True)
            try:
                png = _generate_via_sdk(api_key, settings.GEMINI_IMAGE_MODEL, prompt)
                print(f"[gemini-image] DEBUG: fallback SDK returned {len(png)} bytes", flush=True)
            except ImportError:
                png = _generate_via_rest(api_key, settings.GEMINI_IMAGE_MODEL, prompt)
                print(f"[gemini-image] DEBUG: fallback REST returned {len(png)} bytes", flush=True)
            except GeminiError:
                raise
            except Exception as exc2:
                print(f"[gemini-image] DEBUG: fallback error: {exc2}", flush=True)
                raise GeminiError(f"Gemini generation failed: {exc2}") from exc2
        else:
            raise GeminiError(f"Gemini generation failed: {exc}") from exc

    saved_path = _save_generated_png(png)
    return {"path": saved_path, "prompt": prompt}


def validate_api_key(api_key: str) -> bool:
    if not api_key:
        return False
    # REST check is the most reliable cross-environment validator.
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        r = requests.get(url, timeout=10)
        return r.status_code == 200
    except Exception:
        return False