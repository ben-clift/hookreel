"""Login, secrets and small helpers shared by every page."""
import os
import tempfile
from datetime import datetime, timezone

import streamlit as st

import config
import store

TMP = os.path.join(tempfile.gettempdir(), "hookreel")
os.makedirs(TMP, exist_ok=True)


def secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def guest_logins() -> dict:
    try:
        return dict(st.secrets.get("logins", {}))
    except Exception:
        return {}


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def renders_today(user: str) -> int:
    return sum(1 for r in store.read("renders") if r.get("user") == user and str(r.get("ts", ""))[:10] == today())


def login_gate() -> None:
    if st.session_state.get("ok"):
        return
    app_password = secret("APP_PASSWORD")
    if not app_password and not guest_logins():
        st.session_state.update(ok=True, user=config.ADMIN_NAME, local=True)
        return
    st.title(config.APP_TITLE)
    with st.form("login"):
        name = st.text_input("Name")
        pw = st.text_input("Password", type="password")
        go = st.form_submit_button("Log in")
    if go:
        n = name.strip()
        guests = {k.lower(): v for k, v in guest_logins().items()}
        if n.lower() == config.ADMIN_NAME.lower() and app_password and pw == app_password:
            st.session_state.update(ok=True, user=config.ADMIN_NAME)
            st.rerun()
        elif n.lower() in guests and pw == str(guests[n.lower()]):
            st.session_state.update(ok=True, user=n.title())
            st.rerun()
        else:
            st.error("Name or password not recognised.")
    st.stop()


def boot() -> tuple[str, bool]:
    """Call right after st.set_page_config on every page. Returns (user, is_admin)."""
    store.configure(secret("SUPABASE_URL"), secret("SUPABASE_KEY"))
    login_gate()
    user = st.session_state.get("user", config.ADMIN_NAME)
    return user, user.lower() == config.ADMIN_NAME.lower()
