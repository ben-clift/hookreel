import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from PIL import Image, ImageDraw
from streamlit.testing.v1 import AppTest

import adlib
import config
import script_writer
import shotlib
import store
from test_app import make_sample

HERE = os.path.dirname(os.path.dirname(__file__))
PAGE = os.path.join(HERE, "pages", "1_Screenshots_to_ad.py")


def shots(d, n=3, size=(1170, 2532)):
    out = []
    for i in range(n):
        im = Image.new("RGB", size, (40 * i + 60, 150, 220 - 40 * i))
        ImageDraw.Draw(im).rectangle((100, 300, 600, 700), fill=(255, 255, 255))
        p = os.path.join(d, f"s{i}.png")
        im.save(p)
        out.append(p)
    return out


# ------------------------------------------------------------- script writer
class FakeClient:
    def __init__(self, text):
        self.messages = SimpleNamespace(create=lambda **kw: SimpleNamespace(content=[SimpleNamespace(text=text)]))


def test_script_from_claude_is_cleaned():
    txt = 'Sure! {"hook": "Meet Paw Pop", "shots": [{"caption": "Pop tiles", "motion": "zoom_in"}, {"caption": "Dogs run", "motion": "fly"}]}'
    r = script_writer.write_script("Paw Pop", "puzzle", "Funny", 3, client=FakeClient(txt))
    assert r["ai"] and r["hook"] == "Meet Paw Pop" and len(r["shots"]) == 3
    assert all(s["motion"] in config.MOTIONS for s in r["shots"])  # unknown move replaced, missing shot filled


def test_script_falls_back_without_key_or_on_bad_reply():
    assert script_writer.write_script("X", "y", "Funny", 3)["ai"] is False
    assert script_writer.write_script("X", "y", "Funny", 3, client=FakeClient("not json"))["ai"] is False

    class Boom:
        messages = SimpleNamespace(create=lambda **k: (_ for _ in ()).throw(RuntimeError("down")))

    r = script_writer.write_script("X", "y", "Funny", 2, client=Boom())
    assert r["ai"] is False and len(r["shots"]) == 2


# ------------------------------------------------------------------ montage
def test_montage_every_motion_and_real_clip():
    d = tempfile.mkdtemp()
    imgs = shots(d, 6)
    clip = os.path.join(d, "clip.mp4")
    make_sample(clip, 1170, 2532, 4)
    out, starts = shotlib.build_montage(imgs + [clip], config.MOTIONS + ["x"], 2.5, os.path.join(d, "m.mp4"))
    info = adlib.probe(out)
    assert starts[:3] == [0, 2.5, 5.0] and len(starts) == 7
    assert abs(info.duration - 17.5) < 0.6 and info.width == 1080


def test_custom_animator_can_replace_motion():
    d = tempfile.mkdtemp()
    imgs = shots(d, 2)
    calls = []

    def fake(image, motion, seconds, size, out):
        calls.append(image)
        return shotlib.render_shot(image, "zoom_in", seconds, size, out)

    shotlib.build_montage(imgs, ["pan_up", "pan_up"], 2.5, os.path.join(d, "m.mp4"), animate=fake)
    assert calls == imgs


# --------------------------------------------------------------------- page
def page(user, paths=None):
    at = AppTest.from_file(PAGE, default_timeout=180)
    at.secrets["APP_PASSWORD"] = "pw"
    at.secrets["logins"] = {"Simon": "gpw"}
    at.session_state["ok"] = True
    at.session_state["user"] = user
    if paths:
        at.session_state["ss_paths"] = paths
        at.session_state["ss_key"] = "k1"
    return at


def test_page_needs_screenshots_first():
    at = page("Simon").run()
    assert not at.exception and any("Upload at least" in i.value for i in at.info)


def test_page_script_button_and_make_ad():
    d = tempfile.mkdtemp()
    paths = shots(d, 3)
    store._mem.clear()
    at = page("Simon", paths).run()
    assert not at.exception
    at.text_input(key="ss_name").set_value("Paw Pop")
    at.button[0].click().run()  # Write my script (no key here, so the template)
    assert at.text_input(key="ss_hook").value and at.text_input(key="ss_cap0").value
    at.text_input(key="ss_cap1").set_value("Watch the dogs go")
    at.slider(key="ss_secs").set_value(2.5)
    names = [b.label for b in at.button]
    at.button[names.index("Make my ad")].click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    out = at.session_state["ss_out"]
    info = adlib.probe(out)
    assert abs(info.duration - (7.5 + config.END_CARD_SECONDS)) < 0.7 and (info.width, info.height) == (1080, 1920)
    rec = store.read("renders")
    assert len(rec) == 1 and rec[0]["mode"] == "screenshots" and rec[0]["shots"] == 3
