"""
Shared client for the Zettalgor chat-completions API.

Replaces apps/content_plans/services/zettalgor.py + apps/posts/views.py
inline Zettalgor calls.
"""
import json
import re

import requests

from src.core.config import settings


class ZettalgorError(Exception):
    pass


def _post(prompt: str, *, system_prompt: str = "", timeout: int = 60, json_mode: bool = False) -> str:
    url = settings.ZETTALGOR_API_URL
    api_key = settings.ZETTALGOR_API_KEY
    model = settings.ZETTALGOR_MODEL

    if not url:
        raise ZettalgorError("ZETTALGOR_API_URL is not configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict = {"model": model, "messages": messages}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = requests.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise ZettalgorError(f"Zettalgor request failed: {exc}") from exc

    if response.status_code >= 400:
        raise ZettalgorError(
            f"Zettalgor API {response.status_code}: {response.text[:200]}"
        )

    data = response.json()
    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )


def _clean_text(content: str) -> str:
    """Strip backslashes, quotes, and 'Caption:'/'Hashtags:' labels."""
    content = content.replace("\\n", "\n").replace("\\", "").replace('"', "")
    content = re.sub(r"(?i)caption:\s*", "", content)
    content = re.sub(r"(?i)hashtags:\s*", "", content)
    return content.strip()


def generate_caption(topic: str, platform: str, brand_summary: str = "") -> dict:
    """Returns ``{"caption": str, "hashtags": str}``."""
    brand_block = (
        f"\nBrand context: {brand_summary.strip()}\n" if brand_summary.strip() else ""
    )
    prompt = f"""
Generate one social media caption with hashtags.

Platform: {platform}
Topic: {topic}{brand_block}

Return only this format:
Caption: ...
Hashtags: ...
"""
    raw = _post(prompt)
    cleaned = _clean_text(raw)

    caption_lines, hashtag_lines = [], []
    for line in cleaned.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            hashtag_lines.append(line)
        else:
            caption_lines.append(line)

    return {
        "caption": " ".join(caption_lines).strip(),
        "hashtags": " ".join(hashtag_lines).strip(),
    }


def generate_social_content(
    text: str,
    platform: str = "instagram",
    content_type: str = "post",
    tone: str = "friendly",
    language: str = "English",
) -> dict:
    """Generate ready-to-use social media content from free-form user text.

    Returns ``{"caption": str, "hashtags": str, "suggestions": str}``.
    """
    system_prompt = """You are an expert social media content writer.
Create engaging, platform-optimized content from the user's input.
Return ONLY valid JSON in this exact shape:
{
  "caption": "the main post text",
  "hashtags": "#tag1 #tag2 #tag3",
  "suggestions": "short tips on image/video ideas or posting strategy"
}
Do not include markdown, explanations, or extra text outside the JSON."""

    prompt = f"""
User input: {text.strip()}
Platform: {platform}
Content type: {content_type}
Tone: {tone}
Language: {language}
"""
    raw = _post(prompt, system_prompt=system_prompt, json_mode=True, timeout=180)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        # Fallback: return the raw text as caption so the API never crashes
        return {
            "caption": _clean_text(raw),
            "hashtags": "",
            "suggestions": "",
        }


def enhance_description(description: str, website: str = "", title: str = "") -> dict:
    """Stage 1 — AI-enhance a free-form promotion description.

    Returns ``{"description": str}``.
    """
    system_prompt = """You are an expert social media strategist and copywriter.
Improve the user's promotion description so it is clearer, more compelling,
and ready to drive a multi-day social media campaign.
Keep it concise (2-4 sentences). Do NOT add hashtags or emojis unless the
user already used them. Return ONLY valid JSON in this exact shape:
{"description": "the enhanced description"}
Do not include markdown, explanations, or extra text outside the JSON."""
    context_bits = [f"Description: {description.strip()}"]
    if title.strip():
        context_bits.append(f"Title: {title.strip()}")
    if website.strip():
        context_bits.append(f"Website: {website.strip()}")
    prompt = "\n".join(context_bits)

    raw = _post(prompt, system_prompt=system_prompt, json_mode=True, timeout=120)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            return {"description": _clean_text(raw)}
    return {"description": data.get("description", description).strip()}


def generate_batch_captions(
    description: str,
    platforms: list[str],
    scheduled_dates: list[str],
    timezone: str = "UTC",
    website: str = "",
    title: str = "",
) -> list[dict]:
    """Stage 3 — generate one caption per scheduled day.

    Returns a list of ``{"day": int, "scheduled_at": str, "content": str, "hashtags": str}``.
    """
    n = len(scheduled_dates)
    if n == 0:
        return []

    platform_str = ", ".join(platforms) if platforms else "general"
    dates_block = "\n".join(
        f"Day {i + 1}: {scheduled_dates[i]}" for i in range(n)
    )

    system_prompt = f"""You are an expert social media content writer.
Generate exactly {n} social media captions, one per scheduled day, for a
multi-day campaign. Each caption must be unique, engaging, and tailored to
the platform(s): {platform_str}. Vary the angle/hooks across days so the
campaign feels fresh. Keep each caption concise (1-3 sentences) and include
2-5 relevant hashtags in the hashtags field.

Return ONLY valid JSON in this exact shape:
{{
  "items": [
    {{"day": 1, "content": "caption text", "hashtags": "#tag1 #tag2"}},
    {{"day": 2, "content": "caption text", "hashtags": "#tag1 #tag2"}}
  ]
}}
The items array must have exactly {n} entries, in day order.
Do not include markdown, explanations, or extra text outside the JSON."""

    context_bits = [f"Promotion description: {description.strip()}"]
    if title.strip():
        context_bits.append(f"Campaign title: {title.strip()}")
    if website.strip():
        context_bits.append(f"Website: {website.strip()}")
    context_bits.append(f"Timezone: {timezone}")
    context_bits.append(f"Scheduled dates:\n{dates_block}")
    prompt = "\n".join(context_bits)

    raw = _post(prompt, system_prompt=system_prompt, json_mode=True, timeout=180)
    items_raw = []
    try:
        data = json.loads(raw)
        items_raw = data.get("items", [])
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                items_raw = data.get("items", [])
            except json.JSONDecodeError:
                pass

    # Normalize / fill gaps so the API never returns fewer items than days
    result = []
    for i in range(n):
        entry = items_raw[i] if i < len(items_raw) and isinstance(items_raw[i], dict) else {}
        content = entry.get("content") or entry.get("caption") or ""
        if not content:
            content = generate_caption(
                topic=description.strip(), platform=platforms[0] if platforms else "instagram"
            )["caption"]
        hashtags = entry.get("hashtags", "") or ""
        result.append({
            "day": i,
            "scheduled_at": scheduled_dates[i],
            "content": content.strip(),
            "hashtags": hashtags.strip(),
        })
    return result


def regenerate_single_caption(
    description: str,
    platform: str = "instagram",
    prompt: str = "",
    day: int = 0,
    scheduled_at: str = "",
    website: str = "",
    title: str = "",
) -> dict:
    """Stage 3 — regenerate a single day's caption using an optional instruction.

    Returns ``{"content": str, "hashtags": str}``.
    """
    system_prompt = """You are an expert social media content writer.
Generate ONE engaging, platform-optimized social media caption.
Return ONLY valid JSON in this exact shape:
{"content": "caption text", "hashtags": "#tag1 #tag2"}
Do not include markdown, explanations, or extra text outside the JSON."""

    context_bits = [f"Promotion description: {description.strip()}"]
    if title.strip():
        context_bits.append(f"Campaign title: {title.strip()}")
    if website.strip():
        context_bits.append(f"Website: {website.strip()}")
    context_bits.append(f"Platform: {platform}")
    if scheduled_at:
        context_bits.append(f"Scheduled for: {scheduled_at}")
    if prompt.strip():
        context_bits.append(f"User instruction for this post: {prompt.strip()}")
    else:
        context_bits.append("Generate a fresh, different angle from the description.")
    prompt_text = "\n".join(context_bits)

    raw = _post(prompt_text, system_prompt=system_prompt, json_mode=True, timeout=120)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            return {"content": _clean_text(raw), "hashtags": ""}
    return {
        "content": (data.get("content") or data.get("caption") or "").strip(),
        "hashtags": (data.get("hashtags") or "").strip(),
    }


def generate_brand_summary(snapshot: dict, num_topics: int) -> dict:
    """Returns ``{"summary": str, "keywords": [..], "topics": [..]}``."""
    title = snapshot.get("title", "")
    description = snapshot.get("description", "")
    headings = " | ".join(snapshot.get("headings", [])[:20])
    excerpt = (snapshot.get("excerpt") or "")[:3500]

    prompt = f"""
You are a senior social media strategist analysing a brand's website.

Website title: {title}
Meta description: {description}
Headings: {headings}
Body excerpt: {excerpt}

Respond ONLY with valid JSON in this exact shape:
{{
  "summary": "3-sentence brand summary covering what the brand does, who it serves, and tone.",
  "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "topics": ["topic 1", "topic 2", ... {num_topics} topics total]
}}
"""
    raw = _post(prompt, json_mode=True, timeout=90)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ZettalgorError("Zettalgor returned invalid JSON for brand summary")


def generate_ai_reply(
    comment_text: str,
    author: str,
    post_caption: str,
    previous_comments: str,
    platform: str,
    mode: str = "AI",
    tone: str = "friendly",
    keyword_replies: dict | None = None,
    default_reply: str = "Thank you!",
) -> dict:
    """Returns the AI reply dict (reply, type, used_predefined, should_reply)."""
    import datetime
    mode = mode.upper()

    system_prompt = f"""
You are a smart, engaging social media assistant for social media comment replies.

Your task is to reply to a detected comment based on user-selected settings and previous conversation.

Mode: {mode}

If mode = AI:
- Generate short human-like reply
- Max 20 words
- Tone: {tone}
- Stay relevant to comment
- Use emoji only when needed
- Return JSON only

If mode = MANUAL:
- Use predefined reply only
- If keyword match exists, use keyword reply
- else use default reply

IGNORE comments if:
- spam
- duplicate
- only links
- empty
- bot-like

Output format:
{{
 "reply": "",
 "type": "{mode.lower()}",
 "used_predefined": false,
 "should_reply": true
}}
"""

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    user_prompt = f"""
Current Time: {current_time}
Comment: {comment_text}
Author: {author}
Post Caption: {post_caption}
Previous Comments: {previous_comments}
Platform: {platform}
Keyword Replies: {json.dumps(keyword_replies or {})}
Default Reply: {default_reply}
"""
    try:
        raw = _post(user_prompt, system_prompt=system_prompt, json_mode=True, timeout=(10, 60))
        return json.loads(raw)
    except Exception as e:
        print("❌ AI Reply Error:", e)
        return {
            "reply": default_reply,
            "type": "fallback",
            "used_predefined": False,
            "should_reply": True,
        }