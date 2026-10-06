import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("make_video", ROOT / "scripts" / "video" / "make_video.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_narration_fits_three_minutes_and_scenes_exist():
    mv = load()
    words = sum(len(text.split()) for _, _, text in mv.SCENES)
    assert words <= 450  # ≈ 3 min at a calm 150 words per minute
    film = (ROOT / "scripts" / "video" / "film.html").read_text()
    assert all(f'"{name}"(m)' in film or f"{name}(m)" in film for name, _, _ in mv.SCENES)


def test_captions_cover_the_spoken_span_and_srt_is_well_formed():
    mv = load()
    caps = mv.captions("First sentence. A second, longer sentence here! Third?", 0.5, 6.0)
    assert [c["text"] for c in caps] == ["First sentence.", "A second, longer sentence here!", "Third?"]
    assert caps[0]["start"] == 0.5 and all(a["end"] == b["start"] for a, b in zip(caps, caps[1:]))
    text = mv.srt([{"start": 61.25, "end": 3725.5, "text": "x"}])
    assert text.startswith("1\n00:01:01,250 --> 01:02:05,500\nx")
