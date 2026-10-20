import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import adlib
import config
from test_app import make_sample


def test_all_sizes_and_no_end_card():
    d = tempfile.mkdtemp()
    src = os.path.join(d, "s.mp4")
    make_sample(src, 1920, 1080, 6)
    for name, (w, h) in config.ASPECTS.items():
        out = os.path.join(d, f"o{w}x{h}.mp4")
        adlib.build_ad(src, adlib.AdSpec(length=5, hook="Hi 🐶 there", captions=["a", "b"], app_name="X", aspect=name,
                                         end_card=False), out)
        i = adlib.probe(out)
        assert (i.width, i.height) == (w, h) and 4.5 < i.duration < 5.5


def test_text_cleaning_and_timing():
    assert adlib.clean_text("Hi 🐶 there") == "Hi  there"
    t = adlib.caption_timings(["a", "b", "c"], 12, 3)
    assert len(t) == 3 and t[0][1] >= 3 and t[-1][2] <= 12


def test_bad_file():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.mp4")
    open(p, "w").write("not a video")
    try:
        adlib.probe(p)
        assert False
    except adlib.AdError:
        pass
