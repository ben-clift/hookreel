"""Writes the hook, captions and camera moves for a screenshots ad. No Streamlit in here.

Uses Claude when an API key is set; otherwise a plain template. Claude is told to describe only
what the person typed, so the ad never claims features, ratings or rankings the game doesn't have.
"""
from __future__ import annotations

import json
import re

import config

SYSTEM = (
    "You write short, honest advert copy for mobile and desktop games and apps. "
    "Only use facts the person gave you. Never invent features, awards, ratings, rankings, prices, "
    "or claims like 'free', '#1' or 'best'. No emoji. Reply with JSON only."
)


def fallback_script(game: str, desc: str, n_shots: int) -> dict:
    game = (game or "the game").strip()
    hook = config.HOOK_TEMPLATES[0] if not desc else f"Meet {game}"
    caps = ["Take a look inside", "Easy to pick up", "Hard to put down", "Made with care"]
    shots = [{"caption": caps[i % len(caps)], "motion": config.MOTIONS[i % len(config.MOTIONS)],
              "animation": config.DEFAULT_ANIMATION} for i in range(n_shots)]
    return {"hook": hook.replace("{app}", game), "shots": shots, "ai": False}


def _parse(text: str, n_shots: int) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON")
    data = json.loads(m.group(0))
    hook = str(data.get("hook", "")).strip()
    raw = data.get("shots", [])
    if not hook or not isinstance(raw, list) or not raw:
        raise ValueError("incomplete")
    shots = []
    for i in range(n_shots):
        s = raw[i] if i < len(raw) and isinstance(raw[i], dict) else {}
        motion = s.get("motion") if s.get("motion") in config.MOTIONS else config.MOTIONS[i % len(config.MOTIONS)]
        anim = str(s.get("animation", "")).strip() or config.DEFAULT_ANIMATION
        shots.append({"caption": str(s.get("caption", "")).strip(), "motion": motion, "animation": anim})
    return {"hook": hook, "shots": shots, "ai": True}


def write_script(game: str, desc: str, tone: str, n_shots: int, api_key: str = "", client=None,
                 model: str = config.AI_MODEL) -> dict:
    """Return {"hook", "shots": [{"caption", "motion"}], "ai": bool}. Never raises: falls back to a template."""
    if not client and not api_key:
        return fallback_script(game, desc, n_shots)
    prompt = (
        f"Game or app name: {game}\nWhat it is: {desc}\nTone: {tone}\n"
        f"The advert shows {n_shots} real screenshots in order, each with slow camera movement.\n"
        f"Return JSON: {{\"hook\": <opening line, max 8 words>, \"shots\": [{n_shots} objects, each "
        f"{{\"caption\": <max 6 words>, \"motion\": one of {config.MOTIONS}, \"animation\": <what in that "
        f"screenshot could gently move, only characters or background such as animals, leaves, snow, water, "
        f"light; never the game board or interface>}}]}}"
    )
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(model=model, max_tokens=600, system=SYSTEM,
                                      messages=[{"role": "user", "content": prompt}])
        return _parse(resp.content[0].text, n_shots)
    except Exception:
        return fallback_script(game, desc, n_shots)
