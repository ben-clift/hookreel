import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np
import pytest

import adlib
import soundlib
from test_ai_mode import PAGE, shots
from test_app import make_sample


def rms(a, t0, t1):
    seg = a[int(t0 * soundlib.SR):int(t1 * soundlib.SR)]
    return float(np.sqrt(np.mean(seg ** 2)))


def test_koto_is_audible_not_clipping_and_fades():
    a = soundlib.koto_loop(10)
    assert a.shape == (10 * soundlib.SR, 2) and 0.05 < np.abs(a).max() < 1.0
    assert rms(a, 9.5, 10) < rms(a, 1, 3)  # fades out
    assert np.array_equal(a, soundlib.koto_loop(10))  # same every time, so ads are repeatable


def test_barks_land_on_the_shot_changes():
    d = tempfile.mkdtemp()
    wav = soundlib.make_soundtrack(8, [1.0, 4.0], os.path.join(d, "s.wav"), music="none")
    a = soundlib.load_audio(wav)
    assert abs(len(a) / soundlib.SR - 8) < 0.01
    assert rms(a, 1.0, 1.25) > 0.05 and rms(a, 2.0, 3.5) < 0.001 and rms(a, 4.0, 4.25) > 0.05


def test_own_audio_files_are_used_looped_and_faded():
    d = tempfile.mkdtemp()
    tone = os.path.join(d, "t.wav")
    soundlib.write_wav(tone, np.full((soundlib.SR * 2, 2), 0.3, dtype=np.float32))
    wav = soundlib.make_soundtrack(5, [], os.path.join(d, "s.wav"), music="upload", music_path=tone, barks=False)
    a = soundlib.load_audio(wav)
    assert abs(len(a) / soundlib.SR - 5) < 0.01 and rms(a, 0.5, 1.5) > 0.1 and rms(a, 4.9, 5) < rms(a, 0.5, 1.5)


def test_bad_audio_file_gives_plain_error():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.mp3")
    open(p, "w").write("not audio")
    with pytest.raises(adlib.AdError):
        soundlib.load_audio(p)


def test_add_audio_keeps_length_and_adds_real_sound():
    d = tempfile.mkdtemp()
    v = os.path.join(d, "v.mp4")
    make_sample(v, 640, 1136, 6)
    wav = soundlib.make_soundtrack(6, [1.0], os.path.join(d, "s.wav"))
    out = soundlib.add_audio(v, wav, os.path.join(d, "o.mp4"))
    info = adlib.probe(out)
    assert info.has_audio and abs(info.duration - 6) < 0.3
    assert rms(soundlib.load_audio(out), 0, 6) > 0.02


def test_page_default_sound_is_mixed_into_the_ad():
    from streamlit.testing.v1 import AppTest
    d = tempfile.mkdtemp()
    at = AppTest.from_file(PAGE, default_timeout=240)
    at.secrets["APP_PASSWORD"] = "pw"
    at.session_state["ok"] = True
    at.session_state["user"] = "Ben"
    at.session_state["ss_paths"] = shots(d, 2)
    at.session_state["ss_key"] = "k5"
    at.run()
    assert not at.exception
    at.slider(key="ss_secs").set_value(2.5)
    [b for b in at.button if b.label == "Make my ad"][0].click().run()
    assert not at.exception and not at.error, [e.value for e in at.error]
    a = soundlib.load_audio(at.session_state["ss_out"])
    assert rms(a, 0.1, 1.5) > 0.02  # music and the first bark
