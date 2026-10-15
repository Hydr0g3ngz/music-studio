import numpy as np
import soundfile as sf

from music_studio.backends.lyric_anchors import align_anchors
from music_studio.schema import LyricLine, Lyrics, Word


def test_anchor_transfer_keeps_unknown_words_without_fabricating_times(tmp_path, monkeypatch):
    audio = tmp_path / "vocals.wav"
    sf.write(audio, np.zeros(48000), 16000)
    guide = Lyrics(
        language="en",
        timing_method="native",
        segments=[
            LyricLine(
                id="old",
                text="hello bad world",
                start=0.2,
                end=2.8,
                words=[
                    Word(id="a", text="hello", start=0.2, end=0.6),
                    Word(id="b", text="bad", start=1, end=1.5),
                    Word(id="c", text="world", start=2, end=2.8),
                ],
            )
        ],
    )
    calls = []

    def recognize(source, config):
        calls.append(config)
        return guide

    monkeypatch.setattr("music_studio.backends.lyrics.transcribe_whisper", recognize)
    target = Lyrics(
        language="en",
        timing_method="coarse",
        segments=[
            LyricLine(
                id="new",
                text="Hello, brave world!",
                start=0,
                end=3,
            )
        ],
    )
    config = {"language": "en", "seed": 0, "_anchor_guide": str(tmp_path / "guide.json")}
    aligned = align_anchors(audio, target, config)
    assert aligned.segments[0].text == "Hello, brave world!"
    assert [(w.text, w.start, w.end) for w in aligned.segments[0].words] == [
        ("Hello", 0.2, 0.6),
        ("world", 2, 2.8),
    ]
    assert aligned.segments[0].review_reasons
    assert target.segments[0].words == []
    again = align_anchors(audio, target, config)
    assert len(calls) == 1 and "reused: True" in again.warnings[-1]
    align_anchors(audio, target, {**config, "seed": 1})
    assert len(calls) == 2


def test_anchor_transfer_keeps_multicharacter_native_tokens_whole(tmp_path, monkeypatch):
    audio = tmp_path / "vocals.wav"
    sf.write(audio, np.zeros(32000), 16000)
    guide = Lyrics(
        language="zh",
        timing_method="native",
        segments=[
            LyricLine(
                id="old",
                text="你好",
                start=0.2,
                end=1.5,
                words=[Word(id="a", text="你好", start=0.2, end=1.5)],
            )
        ],
    )
    monkeypatch.setattr("music_studio.backends.lyrics.transcribe_whisper", lambda *args: guide)
    target = Lyrics(
        language="zh",
        timing_method="coarse",
        segments=[
            LyricLine(
                id="new",
                text="你好，世界！",
                start=0,
                end=2,
            )
        ],
    )
    result = align_anchors(audio, target, {"language": "zh"}, preserve_lines=True)
    assert result.segments[0].id == "new"
    assert result.segments[0].text == target.segments[0].text
    assert len(result.segments[0].words) == 1
    assert result.segments[0].words[0].text == "你好"


def test_anchor_transfer_does_not_choose_an_earlier_repeated_chorus(tmp_path, monkeypatch):
    audio = tmp_path / "vocals.wav"
    sf.write(audio, np.zeros(70 * 16000), 16000)
    guide = Lyrics(
        language="en",
        timing_method="native",
        segments=[
            LyricLine(
                id=str(offset),
                text="hello world",
                start=offset + 1,
                end=offset + 4,
                words=[
                    Word(id=f"{offset}-a", text="hello", start=offset + 1, end=offset + 2),
                    Word(id=f"{offset}-b", text="world", start=offset + 3, end=offset + 4),
                ],
            )
            for offset in (0, 60)
        ],
    )
    monkeypatch.setattr("music_studio.backends.lyrics.transcribe_whisper", lambda *args: guide)
    target = Lyrics(
        language="en",
        timing_method="coarse",
        segments=[LyricLine(id="target", text="Hello world", start=60, end=70)],
    )
    result = align_anchors(audio, target, {"language": "en"})
    assert [w.start for w in result.segments[0].words] == [61, 63]
