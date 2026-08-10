"""Veo video generation service — replaces apps/content_plans/services/videos.py."""
import time
import uuid

import requests

from src.core.config import settings
from src.services.crypto import decrypt


class VideoGenerationError(Exception):
    pass


PLATFORM_VIDEO_STYLE = {
    "instagram": ("vertical 9:16, trendy, fast-paced", "9:16"),
    "facebook": ("landscape 16:9, friendly, broad appeal", "16:9"),
    "linkedin": ("landscape 16:9, professional, polished", "16:9"),
    "x": ("landscape 16:9, punchy, bold", "16:9"),
    "tiktok": ("vertical 9:16, trendy, fast-paced", "9:16"),
    "youtube": ("landscape 16:9, polished, cinematic", "16:9"),
}


def build_video_prompt(topic: str, platform: str, brand_summary: str = "", override: str = "") -> str:
    """Build a Veo prompt from free-form text (mirrors images.build_prompt)."""
    if override and override.strip():
        return override.strip()
    style, _ = PLATFORM_VIDEO_STYLE.get(platform, ("landscape 16:9, engaging", "16:9"))
    brand_block = f" Brand style: {brand_summary.strip()}." if brand_summary.strip() else ""
    return (
        f"Create a short social media video for: {topic}. "
        f"Format: {style}.{brand_block} Upbeat, engaging, eye-catching. "
        "Smooth motion, clean transitions, no text overlays."
    )


def _aspect_ratio_for(platform: str) -> str:
    """Return the Veo aspect ratio for a platform (default 16:9)."""
    _, ratio = PLATFORM_VIDEO_STYLE.get(platform, ("landscape 16:9, engaging", "16:9"))
    return ratio


def _save_generated_mp4(video_bytes: bytes) -> str:
    """Save standalone generated MP4. Returns path relative to MEDIA_DIR."""
    dir_path = settings.MEDIA_DIR / "generated"
    dir_path.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:12]}.mp4"
    full_path = dir_path / name
    full_path.write_bytes(video_bytes)
    return f"generated/{name}"


def _generate_via_sdk(api_key: str, model: str, prompt: str, aspect_ratio: str = "16:9") -> bytes:
    """Generate a Veo video via the google-genai SDK (long-running operation).

    Polls until the operation is done, then downloads the video bytes.
    """
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)

    # Veo uses a long-running operation. config carries aspect ratio etc.
    config = types.GenerateVideosConfig(
        aspect_ratio=aspect_ratio,
        number_of_videos=1,
    )
    operation = client.models.generate_videos(
        model=model,
        prompt=prompt,
        config=config,
    )

    # Poll until complete
    import time
    elapsed = 0
    while not operation.done and elapsed < settings.GEMINI_VIDEO_TIMEOUT:
        time.sleep(settings.GEMINI_VIDEO_POLL_INTERVAL)
        elapsed += settings.GEMINI_VIDEO_POLL_INTERVAL
        operation = client.operations.get(operation)

    if not operation.done:
        raise VideoGenerationError("Veo video generation timed out")

    # Surface any server-side error from the operation.
    if getattr(operation, "error", None):
        raise VideoGenerationError(f"Veo operation failed: {operation.error}")

    # The generated videos live under response (or result, same object).
    response = operation.response or operation.result
    if not response or not response.generated_videos:
        raise VideoGenerationError("Veo returned no videos (possibly filtered by safety)")

    video = response.generated_videos[0].video
    if not video:
        raise VideoGenerationError("Veo returned an empty video entry")

    # SDK can hand back bytes directly, or a URI we must download.
    if getattr(video, "video_bytes", None):
        return video.video_bytes

    video_bytes = client.files.download(file=video)
    return video_bytes


def _generate_via_rest(api_key: str, model: str, prompt: str) -> tuple[bytes, str]:
    """REST fallback for Veo. Returns (video_bytes, operation_name)."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:predictLongRunning?key={api_key}"
    )
    payload = {"instances": [{"prompt": prompt}]}
    try:
        r = requests.post(url, json=payload, timeout=settings.GEMINI_REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise VideoGenerationError(f"Veo REST call failed: {exc}") from exc
    if r.status_code >= 400:
        raise VideoGenerationError(f"Veo HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    operation_name = data.get("name", "")
    return b"", operation_name


def generate(item, brand_summary: str = "", prompt_override: str = "") -> str:
    """Generate a Veo video for a ContentPlanItem and save it."""
    import time
    from src.services.images import _save_png  # reuse path logic

    record = item.plan.user.ai_key
    if record is None or not record.gemini_key_encrypted:
        raise VideoGenerationError("User has no Gemini key on file")
    api_key = decrypt(record.gemini_key_encrypted)

    model = item.plan.video_model or record.default_video_model or settings.GEMINI_VIDEO_MODEL
    prompt = prompt_override.strip() or (
        f"Create a short social media video for: {item.topic}. "
        f"Brand style: {brand_summary.strip()}. Upbeat, engaging."
    )

    try:
        video_bytes = _generate_via_sdk(api_key, model, prompt, _aspect_ratio_for(item.platform))
    except ImportError:
        raise VideoGenerationError("google-genai SDK required for video generation")
    except Exception as exc:
        raise VideoGenerationError(f"Veo generation failed: {exc}") from exc

    # Save video
    dir_path = settings.MEDIA_DIR / "content_plans" / str(item.plan_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    name = f"{item.id}-{int(time.time())}.mp4"
    (dir_path / name).write_bytes(video_bytes)
    item.video_prompt = prompt
    return f"content_plans/{item.plan_id}/{name}"


def generate_content_video(
    api_key: str,
    text: str,
    platform: str = "instagram",
    brand_summary: str = "",
    model: str = "",
    prompt_override: str = "",
) -> dict:
    """Generate a standalone Veo video from free-form content text.

    Mirrors ``images.generate_content_image``. Returns
    ``{"path": str, "prompt": str}``.

    NOTE: Veo generation is a long-running operation and can take up to
    ``settings.GEMINI_VIDEO_TIMEOUT`` seconds (~10 min). The caller should
    be aware this is a blocking call.
    """
    model = model or settings.GEMINI_VIDEO_MODEL
    prompt = build_video_prompt(text, platform, brand_summary, prompt_override)
    print(f"[veo-video] DEBUG: model={model}, platform={platform}, key_last4=...{api_key[-4:]}", flush=True)
    print(f"[veo-video] DEBUG: prompt={prompt[:100]}...", flush=True)

    try:
        print(f"[veo-video] DEBUG: generating via SDK (long-running)...", flush=True)
        video_bytes = _generate_via_sdk(api_key, model, prompt, _aspect_ratio_for(platform))
        print(f"[veo-video] DEBUG: SDK returned {len(video_bytes)} bytes", flush=True)
    except ImportError:
        raise VideoGenerationError("google-genai SDK required for video generation")
    except VideoGenerationError:
        raise
    except Exception as exc:
        print(f"[veo-video] DEBUG: SDK error: {exc}", flush=True)
        # Retry with default model on 404 / NOT_FOUND (model unavailable)
        if "404" in str(exc) or "NOT_FOUND" in str(exc):
            print(f"[veo-video] DEBUG: retrying with {settings.GEMINI_VIDEO_MODEL}", flush=True)
            try:
                video_bytes = _generate_via_sdk(api_key, settings.GEMINI_VIDEO_MODEL, prompt, _aspect_ratio_for(platform))
                print(f"[veo-video] DEBUG: fallback SDK returned {len(video_bytes)} bytes", flush=True)
            except Exception as exc2:
                print(f"[veo-video] DEBUG: fallback error: {exc2}", flush=True)
                raise VideoGenerationError(f"Veo generation failed: {exc2}") from exc2
        else:
            raise VideoGenerationError(f"Veo generation failed: {exc}") from exc

    saved_path = _save_generated_mp4(video_bytes)
    return {"path": saved_path, "prompt": prompt}