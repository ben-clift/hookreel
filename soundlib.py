"""Sound for the ads: an original Japanese-style plucked-string loop, dog barks at each shot
change, or the person's own audio files. No Streamlit in here.

The built-in music is made from scratch here (Karplus-Strong plucked strings on a Japanese scale),
so there is nothing to license. The built-in bark is a simple synthetic one: for real dog sounds,
upload a recording (see load_audio). Only upload music you have the rights to.
"""
from __future__ import annotations

import subprocess
import wave

import numpy as np

import adlib

SR = 44100


# --------------------------------------------------------------------- helpers
def load_audio(path: str) -> np.ndarray:
    """Any audio or video file -> float32 stereo array at 44.1 kHz, shape (n, 2)."""
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ar", str(SR), "-ac", "2", "-f", "f32le", "-"],
                           check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError:
        raise adlib.AdError("Could not read that audio file.")
    a = np.frombuffer(r.stdout, dtype=np.float32)
    if a.size < SR // 10:
        raise adlib.AdError("That audio file is empty or too short.")
    return a.reshape(-1, 2).copy()


def write_wav(path: str, a: np.ndarray) -> str:
    pcm = (np.clip(a, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


def _stereo(mono: np.ndarray, pan: float = 0.0) -> np.ndarray:
    left, right = np.sqrt((1 - pan) / 2), np.sqrt((1 + pan) / 2)
    return np.stack([mono * left, mono * right], axis=1).astype(np.float32)


# ----------------------------------------------------------------------- music
# Miyako-bushi ("in") scale, the classic koto sound: D Eb G A Bb
_SCALE = [293.66, 311.13, 392.00, 440.00, 466.16]


def _pluck(freq: float, seconds: float, brightness: float = 0.5, rng=None) -> np.ndarray:
    """Karplus-Strong plucked string, built one period at a time (fast)."""
    rng = rng or np.random.default_rng(1)
    n = int(SR * seconds)
    period = max(int(round(SR / freq)), 2)
    block = rng.uniform(-1, 1, period)
    block = np.convolve(block, np.ones(3) / 3, mode="same") if brightness < 0.5 else block
    out = np.empty(((n // period) + 2) * period)
    for k in range(len(out) // period):
        out[k * period:(k + 1) * period] = block
        block = 0.9965 * 0.5 * (block + np.roll(block, 1))
    out = out[:n]
    out *= np.exp(-np.linspace(0, 3.2, n))
    return out


def koto_loop(seconds: float, bpm: int = 78, seed: int = 7) -> np.ndarray:
    """A calm, original plucked-string melody on a Japanese scale, ending on a fade."""
    rng = np.random.default_rng(seed)
    total = int(SR * (seconds + 2))
    mix = np.zeros((total, 2), dtype=np.float32)
    beat = 60.0 / bpm
    step = beat / 2  # eighth notes
    degrees = [0, 2, 3, 2, 4, 3, 2, 0]  # opening shape, then a gentle random walk
    deg, t, i = 2, 0.0, 0
    while t < seconds + 0.5:
        if i < len(degrees):
            deg = degrees[i]
        else:
            deg = int(np.clip(deg + rng.choice([-2, -1, -1, 0, 1, 1, 2]), 0, 9))
        if rng.random() > 0.18:  # a few rests so it breathes
            f = _SCALE[deg % 5] * (2 if deg >= 5 else 1)  # degrees 5-9 are the octave above
            note = _pluck(f, 1.6, rng=rng) * 0.32
            s = int(t * SR)
            mix[s:s + len(note)] += _stereo(note, pan=rng.uniform(-0.35, 0.35))[: max(0, total - s)]
        if i % 8 == 0:  # low drone pluck on the bar
            low = _pluck(_SCALE[0] / 2, 2.4, rng=rng) * 0.28
            s = int(t * SR)
            mix[s:s + len(low)] += _stereo(low)[: max(0, total - s)]
        t += step
        i += 1
    mix = mix[: int(SR * seconds)]
    fade = int(SR * min(1.2, seconds / 3))
    mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return mix


# ------------------------------------------------------------------------ barks
def synth_bark(pitch: float = 1.0) -> np.ndarray:
    """A simple synthetic 'woof'. It is a placeholder: real recordings sound better."""
    n = int(SR * 0.24)
    t = np.arange(n) / SR
    f0 = (520 - 170 * (t / 0.24)) * pitch
    phase = 2 * np.pi * np.cumsum(f0) / SR
    sig = np.zeros(n)
    for h in range(1, 14):
        fh = np.maximum(f0 * h, 1)
        gain = (1 / h) * (1 + 2.2 * np.exp(-((fh - 750) / 350) ** 2) + 1.4 * np.exp(-((fh - 1700) / 500) ** 2))
        sig += gain * np.sin(h * phase)
    noise = np.random.default_rng(3).normal(0, 1, n)
    noise = np.convolve(noise, np.ones(4) / 4, mode="same") - np.convolve(noise, np.ones(40) / 40, mode="same")
    sig = sig / np.max(np.abs(sig)) + 0.25 * noise / np.max(np.abs(noise))
    env = np.minimum(t / 0.008, 1) * np.exp(-t / 0.075)
    out = sig * env
    return _stereo(out / np.max(np.abs(out)) * 0.8)


def level(mix: np.ndarray, target_rms: float = 0.1, ceiling: float = 0.95) -> np.ndarray:
    """Bring the average loudness up to a sensible level for social feeds without clipping."""
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    rms = float(np.sqrt(np.mean(mix ** 2))) if mix.size else 0.0
    if peak <= 0 or rms <= 0:
        return mix
    return mix * min(ceiling / peak, target_rms / rms)


def place(mix: np.ndarray, clip: np.ndarray, at: float, gain: float) -> None:
    s = int(at * SR)
    if s >= len(mix):
        return
    seg = clip[: len(mix) - s] * gain
    mix[s:s + len(seg)] += seg


# -------------------------------------------------------------------- soundtrack
def make_soundtrack(length: float, bark_times: list[float], out_wav: str, music: str = "koto",
                    music_path: str | None = None, bark_path: str | None = None, barks: bool = True,
                    music_gain: float = 0.8, bark_gain: float = 0.9) -> str:
    """Music (built in or uploaded) plus barks, as a finished wav of exactly `length` seconds."""
    n = int(SR * length)
    if music == "none":
        mix = np.zeros((n, 2), dtype=np.float32)
    elif music == "upload" and music_path:
        a = load_audio(music_path)
        reps = int(np.ceil(n / len(a)))
        mix = np.tile(a, (reps, 1))[:n] * music_gain
        fade = int(SR * min(1.2, length / 3))
        mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
    else:
        mix = koto_loop(length)[:n] * music_gain
        if len(mix) < n:
            mix = np.pad(mix, ((0, n - len(mix)), (0, 0)))
    if barks:
        clip = load_audio(bark_path) if bark_path else None
        for i, t in enumerate(bark_times):
            if clip is not None:
                place(mix, clip[: int(SR * 1.5)], t, bark_gain)
            else:  # "woof woof" with a slightly different second bark
                place(mix, synth_bark(1.0 + 0.04 * (i % 3)), t, bark_gain)
                place(mix, synth_bark(1.12 + 0.04 * (i % 3)), t + 0.3, bark_gain * 0.85)
    return write_wav(out_wav, level(mix))


def add_audio(video_in: str, wav: str, video_out: str) -> str:
    """Replace the (silent) audio track with the soundtrack. Video is copied, not re-encoded."""
    adlib._run(["ffmpeg", "-y", "-v", "error", "-i", video_in, "-i", wav, "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", video_out])
    return video_out
