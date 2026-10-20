"""Video engine for the Ad Maker. Plain Python plus ffmpeg, no Streamlit.

Pipeline: trim a clip -> fit it onto a blurred background at the chosen size ->
burn in a hook line and captions -> add an end card -> join the two parts.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass, field

import config


class AdError(Exception):
    """A problem we can explain to the person in plain words."""


# ------------------------------------------------------------------ helpers
def _run(cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise AdError("ffmpeg is not installed. Add it to packages.txt (Streamlit Cloud) or install it locally.")
    except subprocess.TimeoutExpired:
        raise AdError("Making the ad took too long. Try a shorter clip.")
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or "").strip().splitlines()[-6:]
        raise AdError("ffmpeg could not process that video: " + " | ".join(tail))


def ffmpeg_ok() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def find_font() -> str:
    for p in config.FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise AdError("No bold font found. Add fonts-dejavu-core to packages.txt.")


_EMOJI = re.compile("[\u2190-\u2BFF\U0001F000-\U0010FFFF\uFE0F\u200d]")


def clean_text(s: str) -> str:
    """The burned-in font has no emoji, so strip them rather than show boxes."""
    s = _EMOJI.sub("", s or "")
    return s.replace("\r", "").strip()


def wrap(text: str, width: int) -> str:
    out = []
    for para in clean_text(text).split("\n"):
        out.extend(textwrap.wrap(para, width=width) or [""])
    return "\n".join(out)


def _hex(c: str) -> str:
    return "0x" + c.lstrip("#")


# ------------------------------------------------------------------- probing
@dataclass
class VideoInfo:
    duration: float
    width: int
    height: int
    has_audio: bool


def probe(path: str) -> VideoInfo:
    r = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path], timeout=60)
    data = json.loads(r.stdout or "{}")
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v:
        raise AdError("That file has no video in it.")
    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = rot or int(v.get("tags", {}).get("rotate", 0) or 0)
    if abs(rot) % 180 == 90:
        w, h = h, w
    dur = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    if dur <= 0 or w <= 0:
        raise AdError("Could not read the length of that video.")
    return VideoInfo(dur, w, h, has_audio)


def find_best_start(path: str, length: float, duration: float) -> float:
    """Pick the window with the most on-screen change (a cheap 'where is the action' guess)."""
    length = min(length, duration)
    if duration <= length + 0.5:
        return 0.0
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-an", "-vf",
           "fps=5,scale=320:-2,select='gt(scene,0.02)',metadata=print:file=-", "-f", "null", "-"]
    r = _run(cmd, timeout=300)
    times, scores, t = [], [], None
    for line in r.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            t = float(m.group(1))
        m = re.search(r"scene_score=([\d.]+)", line)
        if m and t is not None:
            times.append(t)
            scores.append(float(m.group(1)))
            t = None
    if not times:
        return 0.0
    best, best_s, s = 0.0, -1.0, 0.0
    start_max = duration - length
    while s <= start_max + 1e-6:
        total = sum(sc for tm, sc in zip(times, scores) if s <= tm < s + length)
        if s < 1.0:
            total *= 0.8  # skip menus and loading at the very start
        if total > best_s:
            best, best_s = s, total
        s += 0.5
    return round(best, 1)


# ---------------------------------------------------------------------- spec
@dataclass
class AdSpec:
    start: float = 0.0
    length: float = config.DEFAULT_CLIP_SECONDS
    hook: str = ""
    captions: list[str] = field(default_factory=list)
    app_name: str = ""
    tagline: str = ""
    cta: str = config.DEFAULT_CTA
    badge: str = config.DEFAULT_BADGE
    theme: str = "Cosy autumn"
    aspect: str = next(iter(config.ASPECTS))
    keep_audio: bool = True
    icon_path: str | None = None
    end_card: bool = True
    caption_spans: list | None = None  # optional [(text, start, end)] to line captions up with shots


def caption_timings(captions: list[str], length: float, hook_secs: float) -> list[tuple[str, float, float]]:
    caps = [clean_text(c) for c in captions if clean_text(c)]
    if not caps:
        return []
    first = hook_secs if hook_secs < length * 0.5 else 0.0
    span = max(length - first - 0.3, 1.0) / len(caps)
    return [(c, first + i * span + 0.05, first + (i + 1) * span - 0.05) for i, c in enumerate(caps)]


# -------------------------------------------------------------------- render
def _drawtext(textfile, fontfile, size, fg, x, y, box=None, border=24, enable=None, spacing=10):
    parts = [f"fontfile={fontfile}", f"textfile={textfile}", f"fontsize={size}", f"fontcolor={_hex(fg)}",
             f"x={x}", f"y={y}", f"line_spacing={spacing}"]
    if box:
        parts += ["box=1", f"boxcolor={_hex(box[0])}@{box[1]}", f"boxborderw={border}"]
    if enable:
        parts.append(f"enable='between(t,{enable[0]:.2f},{enable[1]:.2f})'")
    return "drawtext=" + ":".join(parts)


def _write(tmp: str, name: str, text: str) -> str:
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def _rounded_icon(src: str, dst: str, size: int = 360) -> str:
    try:
        from PIL import Image, ImageDraw
        im = Image.open(src).convert("RGBA").resize((size, size))
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size, size), radius=int(size * 0.225), fill=255)
        im.putalpha(mask)
        im.save(dst)
        return dst
    except Exception:
        return src


_ENC_V = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
          "-video_track_timescale", "30000"]
_ENC_A = ["-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2"]


def _main_segment(src: str, info: VideoInfo, spec: AdSpec, out: str, tmp: str) -> None:
    W, H = config.ASPECTS[spec.aspect]
    th = config.THEMES[spec.theme]
    font = find_font()
    L = round(min(spec.length, info.duration - spec.start), 2)
    vertical = H > W
    margin = int(W * 0.06)
    base = min(W, H)
    box_h = int(H * (0.78 if vertical else 0.70))
    fg_y = f"(H-h)/2+{int(H * 0.03) if vertical else int(H * 0.08)}"
    hook_size = int(base * 0.058)
    cap_size = int(base * 0.046)
    wrap_hook = max(int(W / (hook_size * 0.62)) - 2, 8)
    wrap_cap = max(int(W / (cap_size * 0.62)) - 3, 10)

    chain = [
        "[0:v]split=2[bg][fg]",
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:6,eq=brightness=-0.18[b]",
        f"[fg]scale={W - 2 * margin}:{box_h}:force_original_aspect_ratio=decrease[f]",
        f"[b][f]overlay=(W-w)/2:{fg_y}[v0]",
    ]
    label, n = "v0", 0
    filters = []
    hook = clean_text(spec.hook)
    if hook:
        p = _write(tmp, "hook.txt", wrap(hook, wrap_hook))
        filters.append(_drawtext(p, font, hook_size, th["hook_fg"], "(w-text_w)/2", int(H * 0.04),
                                 box=(th["hook_bg"], 1.0), border=int(hook_size * 0.5),
                                 enable=(0.15, min(config.HOOK_SECONDS, L * 0.5)), spacing=12))
    spans = spec.caption_spans or caption_timings(spec.captions, L, config.HOOK_SECONDS if hook else 0)
    for i, (c, a, b) in enumerate((clean_text(t), a, min(b, L)) for t, a, b in spans if clean_text(t)):
        p = _write(tmp, f"cap{i}.txt", wrap(c, wrap_cap))
        filters.append(_drawtext(p, font, cap_size, th["cap_fg"], "(w-text_w)/2", int(H * (0.80 if vertical else 0.84)),
                                 box=(th["cap_bg"], 0.65), border=int(cap_size * 0.45), enable=(a, b)))
    filters.append(f"fade=t=in:d=0.3,fade=t=out:st={max(L - 0.3, 0):.2f}:d=0.3")
    chain.append(f"[{label}]" + ",".join(filters) + "[v]")

    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{spec.start:.2f}", "-t", f"{L:.2f}", "-i", src]
    if spec.keep_audio and info.has_audio:
        chain.append(f"[0:a]afade=t=in:d=0.3,afade=t=out:st={max(L - 0.5, 0):.2f}:d=0.5,"
                     "aformat=sample_rates=44100:channel_layouts=stereo[a]")
    else:
        cmd += ["-f", "lavfi", "-t", f"{L:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        chain.append("[1:a]anull[a]")
    cmd += ["-filter_complex", ";".join(chain), "-map", "[v]", "-map", "[a]", "-t", f"{L:.2f}",
            *_ENC_V, *_ENC_A, out]
    _run(cmd)


def _end_segment(spec: AdSpec, out: str, tmp: str) -> None:
    W, H = config.ASPECTS[spec.aspect]
    th = config.THEMES[spec.theme]
    font = find_font()
    E = config.END_CARD_SECONDS
    vertical = H > W
    b = min(W, H)
    name_size = int(b * 0.095)
    tag_size = int(b * 0.04)
    cta_size = int(b * 0.055)
    badge_size = int(b * 0.032)
    icon_size = int(b * 0.3)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={_hex(th['bg'])}:s={W}x{H}:r=30:d={E}",
           "-f", "lavfi", "-t", str(E), "-i", "anullsrc=r=44100:cl=stereo"]
    chain = []
    base = "[0:v]"
    has_icon = bool(spec.icon_path and os.path.exists(spec.icon_path))
    if has_icon:
        icon = _rounded_icon(spec.icon_path, os.path.join(tmp, "icon.png"), icon_size)
        cmd += ["-loop", "1", "-t", str(E), "-i", icon]
        chain.append(f"[2:v]scale={icon_size}:{icon_size}[ic]")
    name = clean_text(spec.app_name)
    tag = clean_text(spec.tagline)
    cta = clean_text(spec.cta)
    badge = clean_text(spec.badge)
    gap = int(H * 0.035)
    heights = []  # (kind, height)
    if has_icon:
        heights.append(("icon", icon_size))
    if name:
        heights.append(("name", int(name_size * 1.3)))
    if tag:
        heights.append(("tag", int(tag_size * 1.3)))
    if cta:
        heights.append(("cta", int(cta_size * 1.9)))
    if badge:
        heights.append(("badge", int(badge_size * 1.3)))
    total = sum(h for _, h in heights) + gap * max(len(heights) - 1, 0)
    y0 = max(int((H - total) / 2 - H * 0.02), int(H * 0.04))
    pos = {}
    for kind, h in heights:
        pos[kind] = y0
        y0 += h + gap
    if has_icon:
        chain.append(f"{base}[ic]overlay=(W-w)/2:{pos['icon']}[bgi]")
        base = "[bgi]"
    fx = []
    if name:
        fx.append(_drawtext(_write(tmp, "name.txt", wrap(name, 16)), font, name_size, th["fg"], "(w-text_w)/2", pos["name"]))
    if tag:
        fx.append(_drawtext(_write(tmp, "tag.txt", wrap(tag, 34)), font, tag_size, th["fg"], "(w-text_w)/2", pos["tag"]))
    if cta:
        fx.append(_drawtext(_write(tmp, "cta.txt", cta), font, cta_size, th["hook_fg"] if th["accent"] == th["hook_bg"] else "FFFFFF",
                            "(w-text_w)/2", pos["cta"], box=(th["accent"], 1.0), border=int(cta_size * 0.45)))
    if badge:
        fx.append(_drawtext(_write(tmp, "badge.txt", badge), font, badge_size, th["fg"], "(w-text_w)/2", pos["badge"]))
    fx.append(f"fade=t=in:d=0.3")
    chain.append(f"{base}" + ",".join(fx) + "[v]")
    cmd += ["-filter_complex", ";".join(chain), "-map", "[v]", "-map", "1:a", "-t", str(E), *_ENC_V, *_ENC_A, out]
    _run(cmd)


def build_ad(src: str, spec: AdSpec, out_path: str, info: VideoInfo | None = None) -> str:
    """Make the finished ad at out_path and return it."""
    if not ffmpeg_ok():
        raise AdError("ffmpeg is not installed on this machine.")
    info = info or probe(src)
    spec.length = max(config.MIN_CLIP_SECONDS if info.duration > config.MIN_CLIP_SECONDS else 1,
                      min(spec.length, config.MAX_CLIP_SECONDS, info.duration))
    spec.start = max(0.0, min(spec.start, info.duration - spec.length))
    with tempfile.TemporaryDirectory() as tmp:
        main = os.path.join(tmp, "main.mp4")
        _main_segment(src, info, spec, main, tmp)
        if not spec.end_card:
            shutil.move(main, out_path)
            return out_path
        end = os.path.join(tmp, "end.mp4")
        _end_segment(spec, end, tmp)
        lst = _write(tmp, "list.txt", f"file '{main}'\nfile '{end}'\n")
        _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
              "-movflags", "+faststart", out_path])
    return out_path
