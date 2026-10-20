import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from streamlit.testing.v1 import AppTest

import adlib
import config
import store

HERE = os.path.dirname(os.path.dirname(__file__))


def make_sample(path, w=1170, h=2532, d=8):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r=30:d={d}",
                    "-f", "lavfi", "-i", "sine=f=440:d=%d" % d, "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", path], check=True)


def app(user, sample=None):
    at = AppTest.from_file(os.path.join(HERE, "app.py"), default_timeout=120)
    at.secrets["APP_PASSWORD"] = "pw"
    at.secrets["logins"] = {"Simon": "gpw"}
    at.session_state["ok"] = True
    at.session_state["user"] = user
    if sample:
        info = adlib.probe(sample)
        at.session_state["src_key"] = "t1"
        at.session_state["src_path"] = sample
        at.session_state["info"] = info
        at.session_state["start"] = 0.0
        at.session_state["length"] = 5.0
    return at


def labels(at):
    return [b.label for b in at.button]


def test_admin_and_guest_screens():
    ben = app("Ben").run()
    assert not ben.exception
    assert any("Admin" in e.label for e in ben.expander)
    simon = app("Simon").run()
    assert not simon.exception
    assert not any("Admin" in e.label for e in simon.expander)
    assert any("Ads left today" in c.value for c in simon.caption)


def test_login_rejects_bad_password():
    at = AppTest.from_file(os.path.join(HERE, "app.py"), default_timeout=60)
    at.secrets["APP_PASSWORD"] = "pw"
    at.run()
    at.text_input[0].set_value("Ben")
    at.text_input[1].set_value("wrong")
    at.button[0].click().run()
    assert at.error


def test_make_ad_and_allowance():
    d = tempfile.mkdtemp()
    sample = os.path.join(d, "s.mp4")
    make_sample(sample)
    store._mem.clear()
    at = app("Simon", sample).run()
    assert not at.exception
    at.text_input(key="app_name").set_value("Paw Pop")
    at.text_input(key="hook").set_value("Pop the tiles")
    at.text_area(key="caps").set_value("One\nTwo")
    at.button[[b.label for b in at.button].index("Make my ad")].click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    out = at.session_state["out_path"]
    assert os.path.exists(out)
    assert adlib.probe(out).duration > 7  # 5s clip + 3s end card
    assert len(store.read("renders")) == 1
    assert any("Ads left today: 4" in c.value for c in at.caption)
    # use up the allowance: the button must be disabled
    for _ in range(config.GUEST_DAILY_RENDERS):
        store.append("renders", {"user": "Simon"})
    at.run()
    btn = at.button[[b.label for b in at.button].index("Make my ad")]
    assert btn.disabled


def test_hook_idea_button_sets_text():
    d = tempfile.mkdtemp()
    sample = os.path.join(d, "s.mp4")
    make_sample(sample)
    at = app("Ben", sample).run()
    at.text_input(key="app_name").set_value("Paw Pop")
    at.run()
    at.button(key="hk2").click().run()
    assert at.text_input(key="hook").value == "Why is Paw Pop so addictive?"
