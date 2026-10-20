import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest
from streamlit.testing.v1 import AppTest

import adlib
import config
import providers
import shotlib
import store
from test_ai_mode import PAGE, shots


def fake_video(path, secs=5, w=720, h=1280):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r=24:d={secs}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", path], check=True)
    return path


class Resp:
    def __init__(self, code=200, body=None, content=b"", text=""):
        self.status_code, self._b, self.content, self.text = code, body, content, text

    def json(self):
        return self._b


class FakeHttp:
    """Pretends to be fal's queue: submit, two status checks, result, download."""
    def __init__(self, video_bytes, submit_code=200, fail_result=False):
        self.video, self.submit_code, self.fail_result = video_bytes, submit_code, fail_result
        self.posts, self.polls = [], 0

    def post(self, url, headers=None, json=None, timeout=0):
        self.posts.append((url, headers, json))
        if self.submit_code != 200:
            return Resp(self.submit_code, text="nope")
        return Resp(200, {"request_id": "r1", "status_url": "https://q/status", "response_url": "https://q/result"})

    def get(self, url, headers=None, timeout=0):
        if url == "https://q/status":
            self.polls += 1
            return Resp(200, {"status": "COMPLETED" if self.polls >= 2 else "IN_PROGRESS"})
        if url == "https://q/result":
            return Resp(500, text="boom") if self.fail_result else Resp(200, {"video": {"url": "https://cdn/v.mp4"}})
        return Resp(200, content=self.video)


def test_generate_polls_and_saves(tmp_path):
    d = tempfile.mkdtemp()
    img = shots(d, 1)[0]
    vid = fake_video(os.path.join(d, "v.mp4"))
    http = FakeHttp(open(vid, "rb").read())
    out = providers.fal_generate("KEY", config.AI_VIDEO_DEFAULT, img, "move dogs", os.path.join(d, "o.mp4"), poll=0, http=http)
    assert adlib.probe(out).duration > 4 and http.polls == 2
    url, headers, payload = http.posts[0]
    assert url.endswith(config.AI_VIDEO[config.AI_VIDEO_DEFAULT]["endpoint"])
    assert headers["Authorization"] == "Key KEY" and payload["image_url"].startswith("data:image/jpeg;base64,")
    assert payload["prompt"] == "move dogs" and payload["duration"] == "5"


def test_generate_friendly_errors():
    d = tempfile.mkdtemp()
    img = shots(d, 1)[0]
    with pytest.raises(adlib.AdError, match="rejected the API key"):
        providers.fal_generate("k", config.AI_VIDEO_DEFAULT, img, "p", os.path.join(d, "o.mp4"), poll=0, http=FakeHttp(b"", 401))
    with pytest.raises(adlib.AdError, match="could not finish"):
        providers.fal_generate("k", config.AI_VIDEO_DEFAULT, img, "p", os.path.join(d, "o.mp4"), poll=0,
                               http=FakeHttp(b"", fail_result=True))

    class Down:
        def post(self, *a, **k):
            raise ConnectionError("x")

    with pytest.raises(adlib.AdError, match="Could not reach"):
        providers.fal_generate("k", config.AI_VIDEO_DEFAULT, img, "p", os.path.join(d, "o.mp4"), http=Down())


def test_prompt_guard_and_cost():
    p = providers.build_prompt("the dogs")
    assert "exactly as they are" in p and "the dogs" in p
    assert "falling leaves" in providers.build_prompt("")
    assert providers.estimate_cost(config.AI_VIDEO_DEFAULT, 4) == 1.4


def test_animator_caches_and_passes_real_clips_through():
    d = tempfile.mkdtemp()
    imgs = shots(d, 2)
    clip = fake_video(os.path.join(d, "real.mp4"), 4)
    calls = []

    def gen(key, model, image, prompt, out):
        calls.append(image)
        return fake_video(out, 5)

    cache = os.path.join(d, "cache")
    prompts = {imgs[0]: "dogs", imgs[1]: "leaves"}
    assert providers.uncached_count(imgs + [clip], config.AI_VIDEO_DEFAULT, prompts, cache) == 2
    anim = providers.make_animator("k", config.AI_VIDEO_DEFAULT, prompts, cache, generate=gen)
    out, _ = shotlib.build_montage(imgs + [clip], ["zoom_in"] * 3, 3, os.path.join(d, "m.mp4"), animate=anim)
    assert len(calls) == 2 and abs(adlib.probe(out).duration - 9) < 0.6
    shotlib.build_montage(imgs + [clip], ["zoom_in"] * 3, 3, os.path.join(d, "m2.mp4"), animate=anim)
    assert len(calls) == 2  # second run came from the cache, nothing was paid for again
    assert providers.uncached_count(imgs + [clip], config.AI_VIDEO_DEFAULT, prompts, cache) == 0


def page(user, paths, fal=True):
    at = AppTest.from_file(PAGE, default_timeout=240)
    at.secrets["APP_PASSWORD"] = "pw"
    at.secrets["logins"] = {"Simon": "gpw"}
    if fal:
        at.secrets["FAL_KEY"] = "fk"
    at.session_state["ok"] = True
    at.session_state["user"] = user
    at.session_state["ss_paths"] = paths
    at.session_state["ss_key"] = "k9"
    return at


def test_page_hides_ai_without_key():
    d = tempfile.mkdtemp()
    at = page("Ben", shots(d, 2), fal=False).run()
    assert not at.exception and [o for o in at.radio(key="ss_mode").options] == ["Camera moves only (free)"]
    assert any("AI animation is off" in c.value for c in at.caption)


def test_page_ai_mode_needs_confirmation_then_makes_ad(monkeypatch):
    d = tempfile.mkdtemp()
    paths = shots(d, 2)
    calls = []

    def gen(key, model, image, prompt, out):
        calls.append(prompt)
        return fake_video(out, 5)

    orig = providers.make_animator
    monkeypatch.setattr(providers, "make_animator", lambda k, m, p, c: orig(k, m, p, c, generate=gen))
    store._mem.clear()
    import shutil
    shutil.rmtree(os.path.join(tempfile.gettempdir(), "hookreel", "ai_clips"), ignore_errors=True)  # fresh cache
    at = page("Simon", paths).run()
    assert not at.exception
    at.radio(key="ss_mode").set_value("AI animation (the dogs and scenery really move)").run()
    assert any("about $0.70" in w.value for w in at.warning)
    make = [b for b in at.button if b.label == "Make my ad"][0]
    assert make.disabled  # not until the cost is confirmed
    at.text_input(key="ss_anim0").set_value("the dogs wag their tails")
    at.checkbox(key="ss_confirm").set_value(True).run()
    at.slider(key="ss_secs").set_value(2.5)
    [b for b in at.button if b.label == "Make my ad"][0].click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    assert len(calls) == 2 and "wag their tails" in calls[0] and "exactly as they are" in calls[0]
    rec = store.read("renders")
    assert rec[0]["mode"] == "screenshots-ai"
    assert abs(adlib.probe(at.session_state["ss_out"]).duration - (5 + config.END_CARD_SECONDS)) < 0.7


def test_guest_ai_limit(monkeypatch):
    d = tempfile.mkdtemp()
    store._mem.clear()
    for _ in range(config.AI_GUEST_DAILY_VIDEOS):
        store.append("renders", {"user": "Simon", "mode": "screenshots-ai"})
    at = page("Simon", shots(d, 2)).run()
    at.radio(key="ss_mode").set_value("AI animation (the dogs and scenery really move)").run()
    assert not at.exception
    at.checkbox(key="ss_confirm").set_value(True).run()
    assert [b for b in at.button if b.label == "Make my ad"][0].disabled
