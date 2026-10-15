from types import SimpleNamespace

import numpy as np
import pytest

from music_studio.backends.lyric_alignment import aligned_lines, reference_lyrics, tokens
from music_studio.schema import LyricLine, Lyrics


def test_alignment_preserves_unicode_punctuation_and_uses_acoustic_times():
    line = LyricLine(id="l0", text="你好， don't go!", start=0.1, end=2.5)

    class Model:
        def align(self, *, audio, text, language):
            assert text == "你 好 don't go"
            return [
                [
                    SimpleNamespace(text=t, start_time=start, end_time=end)
                    for t, start, end in [
                        ("你", 0.1, 0.3),
                        ("好", 0.4, 0.8),
                        ("don't", 1.5, 1.6),
                        ("go", 2, 2.5),
                    ]
                ]
            ]

    result, _ = aligned_lines(Model(), np.zeros(48000), [line], "Chinese", 0, 3)
    assert "".join(word.text for word in result[0].words) == line.text
    assert result[0].words[2].start == 1.5
    assert result[0].words[2].end == 1.6


def test_alignment_rejects_zero_duration_and_missing_tokens():
    line = LyricLine(id="l0", text="hello world", start=0.1, end=1)

    class Missing:
        def align(self, **kwargs):
            return [[SimpleNamespace(text="hello", start_time=0.1, end_time=0.5)]]

    with pytest.raises(ValueError, match="字词与输入不一致"):
        aligned_lines(Missing(), np.zeros(32000), [line], "English", 0, 2)

    class Zero:
        def align(self, **kwargs):
            return [
                [SimpleNamespace(text=t, start_time=0.5, end_time=0.5) for t in ("hello", "world")]
            ]

    with pytest.raises(ValueError, match="零长度"):
        aligned_lines(Zero(), np.zeros(32000), [line], "English", 0, 2)


def test_reference_text_requires_match_for_long_audio_and_never_fakes_word_times():
    guide = Lyrics(language="en", timing_method="native", segments=[])
    result = reference_lyrics("Hello, world!\nHello again", guide, 100)
    assert result.segments[0].text == "Hello, world!"
    assert all(not line.words for line in result.segments)
    assert tokens("hello你好") == [("hello", 0, 5), ("你", 5, 6), ("好", 6, 7)]
    with pytest.raises(ValueError, match="匹配不足"):
        reference_lyrics("unrelated words", guide, 600)


def test_partial_reference_alignment_keeps_text_and_omits_unreliable_word_times():
    class Partial:
        def align(self, **kwargs):
            return [
                [
                    SimpleNamespace(text="hello", start_time=0.5, end_time=0.9),
                    SimpleNamespace(text="world", start_time=0.9, end_time=0.9),
                ]
            ]

    line = LyricLine(id="l0", text="hello world", start=0, end=2)
    found, _ = aligned_lines(
        Partial(), np.zeros(32000), [line], "English", 0, 2, sentence_fallback=True
    )
    assert found[0].text == line.text
    assert [(w.text, w.start, w.end) for w in found[0].words] == [("hello ", 0.5, 0.9)]
    assert found[0].review_reasons
    assert found[0].start == 0.5 and found[0].end == 0.9
