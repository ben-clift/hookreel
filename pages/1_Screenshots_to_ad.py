"""Make an ad from real screenshots (and short clips): AI writes the words, the app adds the motion."""
import hashlib
import os
from datetime import datetime

import streamlit as st

import adlib
import common
import config
import providers
import script_writer
import shotlib
import soundlib
import store

st.set_page_config(page_title=config.APP_TITLE + " - Screenshots", page_icon="🎬", layout="centered")
USER, ADMIN = common.boot()
TMP = common.TMP
K = "ss_"  # prefix so this page's widget keys never clash with the main page


def make_script() -> None:  # on_click callback: widget values can only change here
    paths = st.session_state.get(K + "paths", [])
    result = script_writer.write_script(st.session_state.get(K + "name", ""), st.session_state.get(K + "desc", ""),
                                        st.session_state.get(K + "tone", config.TONES[0]), len(paths),
                                        api_key=common.secret("ANTHROPIC_API_KEY"))
    st.session_state[K + "hook"] = result["hook"]
    for i, s in enumerate(result["shots"]):
        st.session_state[f"{K}cap{i}"] = s["caption"]
        st.session_state[f"{K}mot{i}"] = s["motion"]
        st.session_state[f"{K}anim{i}"] = s.get("animation", config.DEFAULT_ANIMATION)
    st.session_state[K + "script_ai"] = result["ai"]


st.title("🎬 " + config.APP_TITLE)
st.subheader("Ad from screenshots")
st.caption(f"Logged in as {USER}" + (" (admin)" if ADMIN else ""))
st.info("Uses only your real screenshots and clips. Nothing is invented: no actors, no fake gameplay, no voices. "
        "The app adds slow camera movement, your words and an end card.")

if not adlib.ffmpeg_ok():
    st.error("ffmpeg is not installed here, so ads can't be made.")
    st.stop()

used = common.renders_today(USER)
left = None if ADMIN else max(config.GUEST_DAILY_RENDERS - used, 0)
if left is not None:
    st.caption(f"Ads left today: {left} of {config.GUEST_DAILY_RENDERS}")
ai_used = sum(1 for r in store.read("renders") if r.get("user") == USER and r.get("mode") == "screenshots-ai"
              and str(r.get("ts", ""))[:10] == common.today())
ai_left = None if ADMIN else max(config.AI_GUEST_DAILY_VIDEOS - ai_used, 0)

# ------------------------------------------------------------- 1. pictures
st.header("1. Your screenshots")
ups = st.file_uploader(f"{config.AI_MIN_SHOTS} to {config.AI_MAX_SHOTS} screenshots, in the order you want them",
                       type=["png", "jpg", "jpeg", "webp", "mp4", "mov", "m4v"], accept_multiple_files=True,
                       help="You can also add a short real gameplay clip. Its first few seconds are used as it is.")
if ups:
    ups = ups[:config.AI_MAX_SHOTS]
    key = hashlib.md5("|".join(f"{u.name}{u.size}" for u in ups).encode()).hexdigest()[:12]
    if st.session_state.get(K + "key") != key:
        paths = []
        for i, u in enumerate(ups):
            p = os.path.join(TMP, f"{key}_{i}_{os.path.basename(u.name)}")
            with open(p, "wb") as f:
                f.write(u.getbuffer())
            paths.append(p)
        for k in [k for k in st.session_state if k.startswith((K + "cap", K + "mot", K + "hook", K + "anim"))]:
            del st.session_state[k]
        st.session_state.update({K + "key": key, K + "paths": paths, K + "out": None})

paths = st.session_state.get(K + "paths", [])
if len(paths) < config.AI_MIN_SHOTS:
    st.info(f"Upload at least {config.AI_MIN_SHOTS} screenshots to begin.")
    st.stop()
stills = [p for p in paths if not shotlib.is_video(p)]
if stills:
    st.image(stills, width=90)

# ------------------------------------------------------------ 2. the game
st.header("2. About the game")
st.text_input("Name", key=K + "name", placeholder="Paw Pop")
st.text_area("What is it? (only say what's true, the ad will repeat it)", key=K + "desc", height=90,
             placeholder="A cosy tile-popping puzzle where you match tiles and dogs run through autumn scenes.")
st.selectbox("Tone", config.TONES, key=K + "tone")
st.button("✨ Write my script", on_click=make_script, type="primary")
if st.session_state.get(K + "script_ai") is False:
    st.caption("Claude is not connected (no ANTHROPIC_API_KEY), so this is a simple template. Edit it freely.")

# ---------------------------------------------------------------- 3. script
st.header("3. Edit the words and moves")
st.text_input("Opening line", key=K + "hook", max_chars=90)
for i, p in enumerate(paths):
    c1, c2 = st.columns([3, 2])
    c1.text_input(f"Caption {i + 1}", key=f"{K}cap{i}", max_chars=60)
    if shotlib.is_video(p):
        c2.selectbox(f"Shot {i + 1}", ["real clip"], key=f"{K}mot{i}", disabled=True)
    else:
        c2.selectbox(f"Move {i + 1}", config.MOTIONS, key=f"{K}mot{i}")
FAL_KEY = common.secret("FAL_KEY")
AI_OK = bool(FAL_KEY)
MODE_FREE, MODE_AI = "Camera moves only (free)", "AI animation (the dogs and scenery really move)"
mode = st.radio("How should it move?", [MODE_FREE, MODE_AI] if AI_OK else [MODE_FREE], key=K + "mode",
                help="AI animation sends each screenshot to an AI video service and costs a little per shot.")
if not AI_OK:
    st.caption("AI animation is off: no FAL_KEY is set in the app's secrets.")
model = config.AI_VIDEO_DEFAULT
prompts = {}
if mode == MODE_AI:
    model = st.selectbox("AI video model", list(config.AI_VIDEO), key=K + "model")
    st.caption("Say what should move. The AI is told to leave the board, tiles and text exactly as they are.")
    for i, p in enumerate(paths):
        if not shotlib.is_video(p):
            prompts[p] = st.text_input(f"What moves in shot {i + 1}", key=f"{K}anim{i}",
                                       placeholder=config.DEFAULT_ANIMATION)
lo, hi, dflt = config.AI_SHOT_SECONDS
st.slider("Seconds per shot", lo, hi, dflt, step=0.5, key=K + "secs")
st.text_input("End card tagline", key=K + "tagline")
c1, c2 = st.columns(2)
c1.text_input("Button text", key=K + "cta", value=config.DEFAULT_CTA)
c2.text_input("Small print", key=K + "badge", value=config.DEFAULT_BADGE)
icon = st.file_uploader("App icon (optional)", type=["png", "jpg", "jpeg"], key=K + "icon_up")

# ----------------------------------------------------------------- 4. sound
st.header("4. Sound")
SND_NONE, SND_BUILTIN, SND_OWN = "No sound", "Japanese-style music (made for you)", "My own music"
snd = st.radio("Music", [SND_BUILTIN, SND_OWN, SND_NONE], key=K + "snd")
barks_on = st.checkbox("Dog barks on each new shot", value=True, key=K + "barks")
music_up = bark_up = None
if snd == SND_OWN:
    music_up = st.file_uploader("Your music (mp3, wav, m4a)", type=["mp3", "wav", "m4a", "aac", "ogg"], key=K + "music_up")
    st.caption("Only use music you own or have the rights to. Platforms often block ads with copyrighted tracks.")
bark_up = st.file_uploader("Your own bark recording (optional, a short clip)", type=["mp3", "wav", "m4a", "ogg"],
                           key=K + "bark_up", help="Without one, a simple synthetic bark is used. A real recording sounds better.")
if snd == SND_BUILTIN:
    st.caption("The music is an original plucked-string loop on a Japanese scale, made by the app, so there is nothing to license.")

# ------------------------------------------------------------------ 5. look
st.header("5. The look")
c1, c2 = st.columns(2)
aspect = c1.selectbox("Size", list(config.ASPECTS), key=K + "aspect")
theme = c2.selectbox("Colours", list(config.THEMES), key=K + "theme")

# ------------------------------------------------------------------ 5. make
st.header("6. Make it")
blocked = left is not None and left <= 0
if blocked:
    st.warning("You have used today's allowance. It resets tomorrow.")
cache_dir = os.path.join(TMP, "ai_clips")
confirmed = True
if mode == MODE_AI:
    n_new = providers.uncached_count(paths, model, prompts, cache_dir)
    cost = providers.estimate_cost(model, n_new)
    if ai_left is not None:
        st.caption(f"AI ads left today: {ai_left} of {config.AI_GUEST_DAILY_VIDEOS}")
        blocked = blocked or ai_left <= 0
    if n_new:
        st.warning(f"This will send {n_new} picture(s) to the AI video service, about ${cost:.2f} in total "
                   "(a rough figure). It also takes a few minutes.")
        confirmed = st.checkbox("Yes, go ahead and spend that", key=K + "confirm")
    else:
        st.caption("Every shot is already made, so this run is free.")
if st.button("Make my ad", type="primary", disabled=blocked or not confirmed):
    secs = float(st.session_state[K + "secs"])
    motions = [st.session_state.get(f"{K}mot{i}", config.MOTIONS[0]) for i in range(len(paths))]
    caps = [st.session_state.get(f"{K}cap{i}", "") for i in range(len(paths))]
    icon_path = None
    if icon is not None:
        icon_path = os.path.join(TMP, f"icon_{hashlib.md5(icon.getvalue()).hexdigest()[:8]}.png")
        with open(icon_path, "wb") as f:
            f.write(icon.getvalue())
    stamp = datetime.now().strftime("%H%M%S")
    out = os.path.join(TMP, f"ad_{st.session_state[K + 'key']}_{stamp}.mp4")
    montage = os.path.join(TMP, f"montage_{stamp}.mp4")
    try:
        with st.spinner("Making your ad, this takes " + ("a few minutes while the AI animates each shot..." if mode == MODE_AI else "about a minute...")):
            animate = (providers.make_animator(FAL_KEY, model, prompts, cache_dir)
                       if mode == MODE_AI else shotlib.render_shot)
            _, starts = shotlib.build_montage(paths, motions, secs, montage, animate=animate)
            spans = [(c, s + 0.1, s + secs - 0.1) for c, s in zip(caps, starts)]
            spec = adlib.AdSpec(
                start=0.0, length=secs * len(paths), hook=st.session_state.get(K + "hook", ""), captions=[],
                caption_spans=spans, app_name=st.session_state.get(K + "name", ""),
                tagline=st.session_state.get(K + "tagline", ""), cta=st.session_state.get(K + "cta", ""),
                badge=st.session_state.get(K + "badge", ""), theme=theme, aspect=aspect, keep_audio=False,
                icon_path=icon_path)
            silent = os.path.join(TMP, f"silent_{stamp}.mp4")
            adlib.build_ad(montage, spec, silent)
            if snd == SND_NONE and not barks_on:
                os.replace(silent, out)
            else:
                total = adlib.probe(silent).duration
                saved = {}
                for name, up in (("music", music_up), ("bark", bark_up)):
                    if up is not None:
                        saved[name] = os.path.join(TMP, f"{name}_{stamp}_{os.path.basename(up.name)}")
                        with open(saved[name], "wb") as f:
                            f.write(up.getvalue())
                times = [s + 0.15 for s in starts] + [secs * len(paths) + 0.2]  # each shot, then the end card
                wav = soundlib.make_soundtrack(
                    total, times, os.path.join(TMP, f"snd_{stamp}.wav"),
                    music={SND_BUILTIN: "koto", SND_OWN: "upload"}.get(snd, "none") if (snd != SND_OWN or "music" in saved) else "koto",
                    music_path=saved.get("music"), bark_path=saved.get("bark"), barks=barks_on)
                soundlib.add_audio(silent, wav, out)
        st.session_state[K + "out"] = out
        saved = store.upload_ad(out, f"{USER.lower()}/{os.path.basename(out)}") if store.enabled() else None
        store.append("renders", {"user": USER, "app": spec.app_name, "aspect": aspect, "theme": theme,
                                 "length": spec.length, "hook": spec.hook, "file": saved,
                                 "mode": "screenshots-ai" if mode == MODE_AI else "screenshots", "shots": len(paths)})
        st.rerun()
    except adlib.AdError as e:
        st.error(str(e))

if st.session_state.get(K + "out") and os.path.exists(st.session_state[K + "out"]):
    st.success("Your ad is ready.")
    st.video(st.session_state[K + "out"])
    with open(st.session_state[K + "out"], "rb") as f:
        st.download_button("Download MP4", f.read(), file_name="ad.mp4", mime="video/mp4")
    st.caption("Sound is mixed in. You can swap it for trending audio when you post.")
