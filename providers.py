"""AI image-to-video through fal.ai. No Streamlit in here.

Each screenshot becomes a short moving clip. The prompt tells the model to leave the board, tiles,
numbers and text alone and to move only what we name (the dogs, falling leaves, snow), so the ad
still shows what the real game looks like. Clips are cached so running the same shot twice is free.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import time

import requests

import adlib
import config
import shotlib

QUEUE = "https://queue.fal.run"
GUARD = ("Keep the game board, tiles, numbers, text and interface exactly as they are in the image. "
         "Only animate: {what}. Smooth, gentle, looping-style motion. No new objects, no scene cuts, "
         "no camera shake.")


def estimate_cost(model: str, n_clips: int) -> float:
    return round(config.AI_VIDEO[model]["cost_per_clip"] * n_clips, 2)


def build_prompt(what: str) -> str:
    return GUARD.format(what=(what or "").strip() or config.DEFAULT_ANIMATION)


def _data_uri(path: str) -> str:
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((1280, 1280))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def fal_generate(api_key: str, model: str, image: str, prompt: str, out_path: str,
                 poll: float = 3.0, timeout: float = 600.0, http=requests) -> str:
    """Make one clip from one image. Raises AdError with a plain message on any problem."""
    m = config.AI_VIDEO[model]
    headers = {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}
    payload = {"prompt": prompt, "image_url": _data_uri(image), **m.get("params", {})}
    try:
        r = http.post(f"{QUEUE}/{m['endpoint']}", headers=headers, json=payload, timeout=60)
        if r.status_code in (401, 403):
            raise adlib.AdError("The AI video service rejected the API key. Check FAL_KEY and that the account has credit.")
        if r.status_code >= 400:
            raise adlib.AdError(f"The AI video service refused the request ({r.status_code}): {r.text[:160]}")
        job = r.json()
        status_url, response_url = job["status_url"], job["response_url"]
        deadline = time.time() + timeout
        while True:
            s = http.get(status_url, headers=headers, timeout=30)
            st = (s.json() or {}).get("status") if s.status_code == 200 else None
            if st == "COMPLETED":
                break
            if s.status_code >= 400 and s.status_code != 429:
                raise adlib.AdError(f"The AI video service stopped with an error ({s.status_code}).")
            if time.time() > deadline:
                raise adlib.AdError("The AI video service took too long. Try again in a minute.")
            time.sleep(poll)
        res = http.get(response_url, headers=headers, timeout=60)
        if res.status_code != 200:
            raise adlib.AdError(f"The AI video service could not finish this shot ({res.status_code}): {res.text[:160]}")
        url = res.json()["video"]["url"]
        data = http.get(url, timeout=120).content
    except adlib.AdError:
        raise
    except Exception as e:  # network trouble, odd replies
        raise adlib.AdError(f"Could not reach the AI video service ({type(e).__name__}).")
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path


def make_animator(api_key: str, model: str, prompts: dict[str, str], cache_dir: str, generate=fal_generate):
    """Return an animate(image, motion, seconds, size, out) function for shotlib.build_montage.

    Real video clips pass straight through. Pictures are animated by the AI, cached by picture,
    model and prompt, then fitted to the ad's size and trimmed to the shot length."""
    os.makedirs(cache_dir, exist_ok=True)

    def animate(image: str, motion: str, seconds: float, size: tuple, out: str) -> str:
        if shotlib.is_video(image):
            return shotlib.render_clip(image, seconds, size, out)
        prompt = build_prompt(prompts.get(image, ""))
        with open(image, "rb") as f:
            key = hashlib.md5(f.read() + model.encode() + prompt.encode()).hexdigest()
        raw = os.path.join(cache_dir, f"{key}.mp4")
        if not os.path.exists(raw):
            tmp = raw[:-4] + ".part.mp4"
            generate(api_key, model, image, prompt, tmp)
            os.replace(tmp, raw)
        return shotlib.render_clip(raw, seconds, size, out)

    return animate


def uncached_count(images: list[str], model: str, prompts: dict[str, str], cache_dir: str) -> int:
    """How many pictures would really be sent to the AI (the rest are cached or are real clips)."""
    n = 0
    for img in images:
        if shotlib.is_video(img):
            continue
        prompt = build_prompt(prompts.get(img, ""))
        with open(img, "rb") as f:
            key = hashlib.md5(f.read() + model.encode() + prompt.encode()).hexdigest()
        if not os.path.exists(os.path.join(cache_dir, f"{key}.mp4")):
            n += 1
    return n
