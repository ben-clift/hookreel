"""Append-only saving on Supabase. No Streamlit in here.

append(kind, record) adds one row to the `records` table (kind + JSON data) in a background
thread. read(kind) returns everything saved plus anything not yet written. Finished ads can be
kept in a private Storage bucket (upload_ad / signed_url). With no Supabase keys everything stays
in memory and status() says so. Set up the table and bucket once with supabase_setup.sql.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import requests

BUCKET = "ads"
CACHE_SECONDS = 60
MAX_ROWS = 5000

_cfg = {"url": "", "key": ""}
_mem: dict[str, list[dict]] = {}
_cache: dict[str, tuple[float, list[dict]]] = {}
_lock = threading.Lock()
_last_error = {"msg": ""}


def configure(url: str = "", key: str = "") -> None:
    _cfg["url"], _cfg["key"] = (url or "").strip().rstrip("/"), (key or "").strip()


def enabled() -> bool:
    return bool(_cfg["url"] and _cfg["key"])


def status() -> str:
    if not enabled():
        return "Saving is OFF (no Supabase keys), records are kept in memory only."
    return "Saving is ON (Supabase)" + (f", last error: {_last_error['msg']}" if _last_error["msg"] else "")


def _h(extra: dict | None = None) -> dict:
    h = {"apikey": _cfg["key"]}
    if not _cfg["key"].startswith("sb_"):  # new sb_secret_ keys are not JWTs: apikey alone, no Bearer header
        h["Authorization"] = f"Bearer {_cfg['key']}"
    h.update(extra or {})
    return h


def _insert(kind: str, rec: dict) -> tuple[bool, str]:
    try:
        r = requests.post(f"{_cfg['url']}/rest/v1/records", headers=_h({"Content-Type": "application/json",
                          "Prefer": "return=minimal"}), json={"kind": kind, "data": rec}, timeout=20)
        return (r.status_code in (200, 201, 204)), f"insert {r.status_code}"
    except Exception as e:  # network errors must never crash the page
        return False, type(e).__name__


def append(kind: str, record: dict, wait: bool = False) -> None:
    rec = dict(record)
    rec.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    with _lock:
        _mem.setdefault(kind, []).append(rec)
        _cache.pop(kind, None)
    if not enabled():
        return

    def work():
        ok, msg = _insert(kind, rec)
        _last_error["msg"] = "" if ok else msg

    t = threading.Thread(target=work, daemon=True)
    t.start()
    if wait:
        t.join(30)


def _remote(kind: str) -> list[dict] | None:
    try:
        r = requests.get(f"{_cfg['url']}/rest/v1/records", headers=_h(),
                         params={"kind": f"eq.{kind}", "select": "data", "order": "id.asc", "limit": MAX_ROWS}, timeout=20)
        if r.status_code != 200:
            _last_error["msg"] = f"read {r.status_code}"
            return None
        return [row["data"] for row in r.json()]
    except Exception as e:
        _last_error["msg"] = type(e).__name__
        return None


def read(kind: str) -> list[dict]:
    with _lock:
        mem = list(_mem.get(kind, []))
    if not enabled():
        return mem
    hit = _cache.get(kind)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        remote = hit[1]
    else:
        got = _remote(kind)
        if got is None:
            return mem
        remote = got
        _cache[kind] = (time.time(), remote)
    seen = {repr(sorted(r.items())) for r in remote}
    return remote + [m for m in mem if repr(sorted(m.items())) not in seen]


# ------------------------------------------------------------------ storage
def upload_ad(local_path: str, name: str) -> str | None:
    """Keep a finished ad in the private bucket. Returns its path, or None if it could not be saved."""
    if not enabled():
        return None
    try:
        with open(local_path, "rb") as f:
            r = requests.post(f"{_cfg['url']}/storage/v1/object/{BUCKET}/{name}",
                              headers=_h({"Content-Type": "video/mp4", "x-upsert": "true"}), data=f, timeout=300)
        if r.status_code in (200, 201):
            return name
        _last_error["msg"] = f"upload {r.status_code}"
    except Exception as e:
        _last_error["msg"] = type(e).__name__
    return None


def signed_url(name: str, seconds: int = 3600) -> str | None:
    if not enabled() or not name:
        return None
    try:
        r = requests.post(f"{_cfg['url']}/storage/v1/object/sign/{BUCKET}/{name}",
                          headers=_h({"Content-Type": "application/json"}), json={"expiresIn": seconds}, timeout=20)
        if r.status_code == 200:
            path = r.json().get("signedURL", "")
            return f"{_cfg['url']}/storage/v1{path}" if path.startswith("/") else None
    except Exception as e:
        _last_error["msg"] = type(e).__name__
    return None


def test_saving() -> str:
    if not enabled():
        return "Saving is OFF: no Supabase URL and key are set, so nothing was saved."
    ok, msg = _insert("tests", {"note": "test saving", "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    if ok:
        _last_error["msg"] = ""
        return "Saved a test record to Supabase."
    hint = " Check the SQL setup was run and the key is the secret (service role) key." if "401" in msg or "404" in msg else ""
    return f"Failed ({msg}).{hint}"
