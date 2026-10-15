import mido
import pytest

from music_studio.export import timestamp, write_midi
from music_studio.schema import LyricLine, Lyrics, Melody, Note, Rhythm, Word


def test_timestamp_carry():
    assert timestamp(59.9996, srt=True) == "00:01:00,000"
    assert timestamp(3599.9996, srt=True) == "01:00:00,000"
    assert timestamp(59.9996) == "01:00.00"


def test_variable_tempo_midi_preserves_real_note_times(tmp_path):
    notes = [
        Note(id="a", start=0.33, end=1.12, pitch=60, score=0.8),
        Note(id="b", start=1.12, end=2.93, pitch=60, score=0.9),
        Note(id="c", start=3.1, end=4.4, pitch=69, score=0.9),
    ]
    melody = Melody(backend="test", notes=notes)
    rhythm = Rhythm(backend="test", bpm=120, beats=[0.2, 0.7, 1.2, 1.8, 2.4, 3.1, 3.8, 4.5])
    lyrics = Lyrics(language=None, timing_method="test", segments=[])
    path = tmp_path / "melody.mid"
    write_midi(path, melody, rhythm, lyrics)
    midi = mido.MidiFile(path)
    starts, ends, time = [], [], 0
    for message in midi:
        time += message.time
        if message.type == "note_on" and message.velocity:
            starts.append(time)
        elif message.type == "note_off":
            ends.append(time)
    assert starts == pytest.approx([n.start for n in notes], abs=0.002)
    assert ends == pytest.approx([n.end for n in notes], abs=0.002)


def test_midi_retains_untimed_text_when_only_some_words_have_anchors(tmp_path):
    lyrics = Lyrics(
        language="en",
        timing_method="anchors",
        segments=[
            LyricLine(
                id="line",
                text="Hello brave world",
                start=0.1,
                end=2,
                words=[Word(id="known", text="Hello", start=0.1, end=0.5)],
            )
        ],
    )
    path = tmp_path / "partial.mid"
    write_midi(
        path, Melody(backend="test", notes=[]), Rhythm(backend="test", bpm=120, beats=[]), lyrics
    )
    events = [
        m.text for t in mido.MidiFile(path, charset="utf-8").tracks for m in t if m.type == "lyrics"
    ]
    assert events == ["Hello brave world"]
