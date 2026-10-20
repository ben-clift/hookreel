"""Turns real screenshots into a moving montage with ffmpeg. No Streamlit in here.

Nothing is invented: each screenshot is only given camera motion (slow zoom or pan). To use an AI
video service instead, pass your own `animate(image, motion, seconds, size, out_path)` function to
build_montage(); the free ffmpeg motion below is the default.
"""
from __future__ import annotations

import os
import tempfile
from typing import Callable

import adlib
import config

FPS = 30
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
       "-video_track_timescale", "30000", "-an"]


VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv")


def is_video(path: str) -> bool:
    return path.lower().endswith(VIDEO_EXT)


def canvas_size(first: str) -> tuple[int, int]:
    """1080 wide, height from the first item's shape (kept even, limited to a sensible range)."""
    if is_video(first):
        info = adlib.probe(first)
        w, h = info.width, info.height
    else:
        from PIL import Image
        with Image.open(first) as im:
            w, h = im.size
    height = int(round(1080 * h / w / 2) * 2)
    return 1080, max(720, min(height, 2160))


def _zoompan(motion: str, n: int) -> str:
    c = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if motion == "zoom_out":
        return f"z='1.25-0.25*on/{n}':{c}"
    if motion == "pan_left":
        return f"z='1.15':x='(iw-iw/zoom)*(1-on/{n})':y='ih/2-(ih/zoom/2)'"
    if motion == "pan_right":
        return f"z='1.15':x='(iw-iw/zoom)*on/{n}':y='ih/2-(ih/zoom/2)'"
    if motion == "pan_up":
        return f"z='1.15':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-on/{n})'"
    if motion == "pan_down":
        return f"z='1.15':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*on/{n}'"
    return f"z='1+0.25*on/{n}':{c}"  # zoom_in (default)


def render_clip(video: str, seconds: float, size: tuple[int, int], out: str) -> str:
    """A real recording: first few seconds, fitted to the canvas, no added motion."""
    W, H = size
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},"
          f"fade=t=in:d=0.15,fade=t=out:st={max(seconds - 0.15, 0):.2f}:d=0.15,format=yuv420p")
    adlib._run(["ffmpeg", "-y", "-v", "error", "-i", video, "-t", f"{seconds:.2f}", "-vf", vf, *ENC, out])
    return out


def render_shot(image: str, motion: str, seconds: float, size: tuple[int, int], out: str) -> str:
    if is_video(image):
        return render_clip(image, seconds, size, out)
    W, H = size
    n = max(int(round(seconds * FPS)), 2)
    vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
          f"zoompan={_zoompan(motion, n)}:d={n}:s={W}x{H}:fps={FPS},"
          f"fade=t=in:d=0.15,fade=t=out:st={max(seconds - 0.15, 0):.2f}:d=0.15,format=yuv420p")
    adlib._run(["ffmpeg", "-y", "-v", "error", "-i", image, "-vf", vf, "-frames:v", str(n), *ENC, out])
    return out


Animate = Callable[[str, str, float, tuple, str], str]


def build_montage(images: list[str], motions: list[str], seconds: float, out_path: str,
                  animate: Animate = render_shot) -> tuple[str, list[float]]:
    """Make one video from screenshots and/or short real clips. Returns (path, start time of each shot)."""
    if not images:
        raise adlib.AdError("Add at least one screenshot.")
    size = canvas_size(images[0])
    starts: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, img in enumerate(images):
            mo = motions[i] if i < len(motions) and motions[i] in config.MOTIONS else config.MOTIONS[0]
            p = os.path.join(tmp, f"s{i}.mp4")
            animate(img, mo, seconds, size, p)
            starts.append(round(i * seconds, 2))
            parts.append(p)
        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w") as f:
            f.write("".join(f"file '{p}'\n" for p in parts))
        adlib._run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out_path])
    return out_path, starts
