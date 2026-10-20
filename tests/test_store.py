import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import store


class Resp:
    def __init__(self, code=200, body=None):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


def fresh(monkeypatch):
    store._mem.clear()
    store._cache.clear()
    store.configure("https://x.supabase.co", "secret")
    calls = []
    db = []

    def post(url, headers=None, json=None, data=None, timeout=0):
        calls.append(("POST", url, headers, json))
        if url.endswith("/rest/v1/records"):
            db.append({"data": json["data"], "kind": json["kind"]})
            return Resp(201)
        if "/object/sign/" in url:
            return Resp(200, {"signedURL": "/object/sign/ads/a.mp4?token=t"})
        return Resp(200)

    def get(url, headers=None, params=None, timeout=0):
        calls.append(("GET", url, headers, params))
        kind = params["kind"].split(".", 1)[1]
        return Resp(200, [{"data": r["data"]} for r in db if r["kind"] == kind])

    monkeypatch.setattr(store.requests, "post", post)
    monkeypatch.setattr(store.requests, "get", get)
    return calls, db


def test_off_without_keys():
    store._mem.clear()
    store.configure("", "")
    assert not store.enabled() and "OFF" in store.status()
    store.append("renders", {"user": "Ben"})
    assert len(store.read("renders")) == 1
    assert "OFF" in store.test_saving()


def test_append_read_roundtrip_no_duplicates(monkeypatch):
    calls, db = fresh(monkeypatch)
    store.append("renders", {"user": "Simon", "ts": "2026-10-20T10:00:00+00:00"}, wait=True)
    assert db[0]["kind"] == "renders" and db[0]["data"]["user"] == "Simon"
    assert calls[0][2]["apikey"] == "secret" and calls[0][2]["Authorization"] == "Bearer secret"  # old JWT-style key
    store._cache.clear()
    assert len(store.read("renders")) == 1  # saved copy and in-memory copy are one record


def test_signed_url_and_test_saving(monkeypatch):
    fresh(monkeypatch)
    assert store.signed_url("a.mp4") == "https://x.supabase.co/storage/v1/object/sign/ads/a.mp4?token=t"
    assert "Saved a test record" in store.test_saving()


def test_failures_do_not_crash(monkeypatch):
    fresh(monkeypatch)

    def boom(*a, **k):
        raise ConnectionError("down")

    monkeypatch.setattr(store.requests, "post", boom)
    monkeypatch.setattr(store.requests, "get", boom)
    store.append("renders", {"user": "Ben"}, wait=True)
    assert len(store.read("renders")) == 1
    assert "Failed" in store.test_saving()
    assert store.upload_ad(__file__, "x.mp4") is None


def test_new_style_secret_key_sends_apikey_only(monkeypatch):
    calls, _ = fresh(monkeypatch)
    store.configure("https://x.supabase.co", "sb_secret_abc")
    store.append("renders", {"user": "Ben"}, wait=True)
    assert calls[0][2]["apikey"] == "sb_secret_abc" and "Authorization" not in calls[0][2]
