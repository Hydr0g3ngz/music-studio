from pathlib import Path

import numpy as np
import soundfile as sf

from music_studio.backends.lyric_retry import retry_line
from music_studio.schema import LyricLine, Lyrics, Word


def test_retry_preserves_other_corrections_and_master_audio_offset(tmp_path, monkeypatch):
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros(16000 * 20), 16000)
    (tmp_path / "analysis").mkdir()
    lyrics = Lyrics(
        language="en",
        timing_method="native",
        segments=[
            LyricLine(id="l0", text="corrected first", start=1, end=2),
            LyricLine(id="l1", text="wrong", start=10, end=12),
            LyricLine(id="l2", text="corrected last", start=15, end=16),
        ],
    )

    def recognize(path: Path, config):
        audio, rate = sf.read(path)
        assert rate == 16000 and len(audio) == 40000
        return Lyrics(
            language="en",
            timing_method="retry",
            segments=[
                LyricLine(
                    id="l0",
                    text="right",
                    start=0.3,
                    end=2,
                    words=[Word(id="w0", text="right", start=0.3, end=2)],
                ),
            ],
        )

    monkeypatch.setattr("music_studio.backends.lyric_retry.transcribe", recognize)
    result = retry_line(source, lyrics, "l1", tmp_path, {})
    assert result.segments[0] == lyrics.segments[0]
    assert result.segments[-1] == lyrics.segments[-1]
    assert result.segments[1].id == "l1"
    assert result.segments[1].text == "right"
    assert result.segments[1].words[0].start == 10.05
    assert lyrics.segments[1].text == "wrong"
