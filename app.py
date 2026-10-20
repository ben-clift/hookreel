"""Hookreel: turn a gameplay or app screen recording into a short ad."""
import hashlib
import os
from datetime import datetime

import streamlit as st

import adlib
import config
import store

st.set_page_config(page_title=config.APP_TITLE, page_icon="🎬", layout="centered")


import common
from common import TMP, renders_today

USER, ADMIN = common.boot()


def pick_hook(text: str) -> None:  # on_click callback: widget values can only change here
    st.session_state["hook"] = text.replace("{app}", st.session_state.get("app_name") or "the game")


def suggest_start() -> None:
    p, info = st.session_state.get("src_path"), st.session_state.get("info")
    if not p or not info:
        return
    try:
        st.session_state["start"] = float(adlib.find_best_start(p, float(st.session_state["length"]), info.duration))
        st.session_state["note"] = "Moved the start to the busiest part of the recording."
    except adlib.AdError as e:
        st.session_state["note"] = str(e)


# ------------------------------------------------------------------- header
top = st.container()
with top:
    st.title("🎬 " + config.APP_TITLE)
    c1, c2 = st.columns([3, 1])
    c1.caption(f"Logged in as {USER}" + (" (admin)" if ADMIN else ""))
    if not st.session_state.get("local") and c2.button("Log out"):
        st.session_state.clear()
        st.rerun()

if not adlib.ffmpeg_ok():
    st.error("ffmpeg is not installed here, so ads can't be made. On Streamlit Cloud add it to packages.txt.")
    st.stop()

used = renders_today(USER)
left = None if ADMIN else max(config.GUEST_DAILY_RENDERS - used, 0)
if left is not None:
    st.caption(f"Ads left today: {left} of {config.GUEST_DAILY_RENDERS}")

# ------------------------------------------------------------------- history
def show_link(path: str) -> None:  # on_click callback
    st.session_state["links"] = {**st.session_state.get("links", {}), path: store.signed_url(path) or "unavailable"}


mine = [r for r in store.read("renders") if r.get("file") and (ADMIN or r.get("user") == USER)]
if mine:
    with st.expander(f"Earlier ads ({len(mine)})"):
        for i, r in enumerate(mine[-8:][::-1]):
            c1, c2 = st.columns([3, 1])
            c1.write(f"{r.get('app') or 'Untitled'}, {str(r.get('ts', ''))[:16].replace('T', ' ')}"
                     + (f" ({r.get('user')})" if ADMIN else ""))
            link = st.session_state.get("links", {}).get(r["file"])
            if link and link != "unavailable":
                c2.link_button("Open", link)
            else:
                c2.button("Get link", key=f"lk{i}", on_click=show_link, args=(r["file"],))

# --------------------------------------------------------------------- admin
if ADMIN:
    with st.expander("Admin"):
        st.caption(store.status())
        if st.button("Test saving"):
            st.info(store.test_saving())
        rows = store.read("renders")
        st.write(f"Ads made so far: {len(rows)}")
        if rows:
            st.dataframe(rows[-50:][::-1], use_container_width=True)

# ---------------------------------------------------------------- 1. upload
st.header("1. Your recording")
up = st.file_uploader("Screen recording of your game or app", type=["mp4", "mov", "m4v", "webm", "mkv"],
                      help=f"Up to {config.MAX_UPLOAD_MB} MB. iPhone and Mac screen recordings both work.")
if up is not None:
    key = hashlib.md5(f"{up.name}{up.size}".encode()).hexdigest()[:12]
    if st.session_state.get("src_key") != key:
        path = os.path.join(TMP, f"{key}_{os.path.basename(up.name)}")
        with open(path, "wb") as f:
            f.write(up.getbuffer())
        try:
            info = adlib.probe(path)
        except adlib.AdError as e:
            st.error(str(e))
            st.stop()
        st.session_state.update(src_key=key, src_path=path, info=info, out_path=None, note="")
        st.session_state["start"] = 0.0
        st.session_state["length"] = float(min(config.DEFAULT_CLIP_SECONDS, info.duration, config.MAX_CLIP_SECONDS))

info = st.session_state.get("info")
if not info:
    st.info("Upload a recording to begin.")
    st.stop()

st.caption(f"{info.width}x{info.height}, {info.duration:.1f}s, {'with' if info.has_audio else 'no'} sound")

# ---------------------------------------------------------------- 2. moment
st.header("2. Pick the moment")
max_len = float(min(config.MAX_CLIP_SECONDS, info.duration))
min_len = float(min(config.MIN_CLIP_SECONDS, max_len))
if min_len < max_len:
    st.slider("Length (seconds)", min_len, max_len, key="length", step=1.0)
else:
    st.session_state["length"] = max_len
length = float(st.session_state["length"])
start_max = max(info.duration - length, 0.0)
st.session_state["start"] = float(min(st.session_state.get("start", 0.0), start_max))
if start_max > 0:
    st.slider("Start at (seconds)", 0.0, float(start_max), key="start", step=0.5)
st.button("Find the busiest moment", on_click=suggest_start)
if st.session_state.get("note"):
    st.caption(st.session_state["note"])
st.video(st.session_state["src_path"], start_time=int(st.session_state["start"]),
         end_time=int(st.session_state["start"] + length))

# ------------------------------------------------------------------ 3. words
st.header("3. The words")
st.text_input("App or game name", key="app_name", placeholder="Paw Pop")
st.text_input("Opening line (shown first, in big letters)", key="hook", max_chars=90)
with st.expander("Opening line ideas"):
    for i, t in enumerate(config.HOOK_TEMPLATES):
        st.button(t.replace("{app}", st.session_state.get("app_name") or "the game"), key=f"hk{i}",
                  on_click=pick_hook, args=(t,))
st.text_area("Captions (one per line, spread evenly across the clip)", key="caps", height=110,
             placeholder="Match the tiles\nWatch the dogs go wild\nRelax, it's cosy")
st.text_input("End card tagline", key="tagline", placeholder="A cosy tile-popping puzzle")
c1, c2 = st.columns(2)
c1.text_input("Button text", key="cta", value=config.DEFAULT_CTA)
c2.text_input("Small print", key="badge", value=config.DEFAULT_BADGE)
icon = st.file_uploader("App icon (optional)", type=["png", "jpg", "jpeg"], key="icon_up")

# ------------------------------------------------------------------- 4. look
st.header("4. The look")
c1, c2 = st.columns(2)
aspect = c1.selectbox("Size", list(config.ASPECTS), key="aspect")
theme = c2.selectbox("Colours", list(config.THEMES), key="theme")
c1, c2 = st.columns(2)
keep_audio = c1.checkbox("Keep the game sound", value=True, disabled=not info.has_audio, key="keep_audio")
end_card = c2.checkbox("Add an end card", value=True, key="end_card")

# ------------------------------------------------------------------- 5. make
st.header("5. Make it")
blocked = left is not None and left <= 0
if blocked:
    st.warning("You have used today's allowance. It resets tomorrow.")
if st.button("Make my ad", type="primary", disabled=blocked):
    icon_path = None
    if icon is not None:
        icon_path = os.path.join(TMP, f"icon_{hashlib.md5(icon.getvalue()).hexdigest()[:8]}.png")
        with open(icon_path, "wb") as f:
            f.write(icon.getvalue())
    spec = adlib.AdSpec(
        start=float(st.session_state["start"]), length=length,
        hook=st.session_state.get("hook", ""),
        captions=[c for c in st.session_state.get("caps", "").splitlines() if c.strip()],
        app_name=st.session_state.get("app_name", ""), tagline=st.session_state.get("tagline", ""),
        cta=st.session_state.get("cta", ""), badge=st.session_state.get("badge", ""),
        theme=theme, aspect=aspect, keep_audio=keep_audio, icon_path=icon_path, end_card=end_card)
    out = os.path.join(TMP, f"ad_{st.session_state['src_key']}_{datetime.now().strftime('%H%M%S')}.mp4")
    try:
        with st.spinner("Making your ad, this takes about a minute..."):
            adlib.build_ad(st.session_state["src_path"], spec, out, info)
        st.session_state["out_path"] = out
        saved = store.upload_ad(out, f"{USER.lower()}/{os.path.basename(out)}") if store.enabled() else None
        store.append("renders", {"user": USER, "app": spec.app_name, "aspect": aspect, "theme": theme,
                                 "length": spec.length, "hook": spec.hook, "file": saved})
        st.rerun()
    except adlib.AdError as e:
        st.error(str(e))

if st.session_state.get("out_path") and os.path.exists(st.session_state["out_path"]):
    st.success("Your ad is ready.")
    st.video(st.session_state["out_path"])
    with open(st.session_state["out_path"], "rb") as f:
        st.download_button("Download MP4", f.read(), file_name="ad.mp4", mime="video/mp4")
