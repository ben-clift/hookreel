"""Make an ad from real screenshots (and short clips): AI writes the words, the app adds the motion."""
import hashlib
import os
from datetime import datetime

import streamlit as st

import adlib
import common
import config
import script_writer
import shotlib
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
        for k in [k for k in st.session_state if k.startswith((K + "cap", K + "mot", K + "hook"))]:
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
lo, hi, dflt = config.AI_SHOT_SECONDS
st.slider("Seconds per shot", lo, hi, dflt, step=0.5, key=K + "secs")
st.text_input("End card tagline", key=K + "tagline")
c1, c2 = st.columns(2)
c1.text_input("Button text", key=K + "cta", value=config.DEFAULT_CTA)
c2.text_input("Small print", key=K + "badge", value=config.DEFAULT_BADGE)
icon = st.file_uploader("App icon (optional)", type=["png", "jpg", "jpeg"], key=K + "icon_up")

# ------------------------------------------------------------------ 4. look
st.header("4. The look")
c1, c2 = st.columns(2)
aspect = c1.selectbox("Size", list(config.ASPECTS), key=K + "aspect")
theme = c2.selectbox("Colours", list(config.THEMES), key=K + "theme")

# ------------------------------------------------------------------ 5. make
st.header("5. Make it")
blocked = left is not None and left <= 0
if blocked:
    st.warning("You have used today's allowance. It resets tomorrow.")
if st.button("Make my ad", type="primary", disabled=blocked):
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
        with st.spinner("Making your ad, this takes about a minute..."):
            _, starts = shotlib.build_montage(paths, motions, secs, montage)
            spans = [(c, s + 0.1, s + secs - 0.1) for c, s in zip(caps, starts)]
            spec = adlib.AdSpec(
                start=0.0, length=secs * len(paths), hook=st.session_state.get(K + "hook", ""), captions=[],
                caption_spans=spans, app_name=st.session_state.get(K + "name", ""),
                tagline=st.session_state.get(K + "tagline", ""), cta=st.session_state.get(K + "cta", ""),
                badge=st.session_state.get(K + "badge", ""), theme=theme, aspect=aspect, keep_audio=False,
                icon_path=icon_path)
            adlib.build_ad(montage, spec, out)
        st.session_state[K + "out"] = out
        saved = store.upload_ad(out, f"{USER.lower()}/{os.path.basename(out)}") if store.enabled() else None
        store.append("renders", {"user": USER, "app": spec.app_name, "aspect": aspect, "theme": theme,
                                 "length": spec.length, "hook": spec.hook, "file": saved,
                                 "mode": "screenshots", "shots": len(paths)})
        st.rerun()
    except adlib.AdError as e:
        st.error(str(e))

if st.session_state.get(K + "out") and os.path.exists(st.session_state[K + "out"]):
    st.success("Your ad is ready.")
    st.video(st.session_state[K + "out"])
    with open(st.session_state[K + "out"], "rb") as f:
        st.download_button("Download MP4", f.read(), file_name="ad.mp4", mime="video/mp4")
    st.caption("This ad has no sound. Add music or a voiceover in your video editor or when you post it.")
