import numpy as np
import pytest
import soundfile as sf

from music_studio.backends.harmony import classify_chroma, estimate_harmony
from music_studio.backends.melody import notes_from_contour, stable_notes_from_contour
from music_studio.backends.rhythm import estimate_rhythm
from music_studio.export import link_words
from music_studio.schema import LyricLine, Lyrics, Melody, Rhythm, Word


def test_note_contour_silence_vibrato_and_repeat():
    time = np.arange(0, 4, 0.01)
    frequency = np.full(len(time), np.nan)
    voiced = (time >= 0.5) & (time < 2.5)
    frequency[voiced] = 440 * 2 ** (0.2 * np.sin(time[voiced] * 2 * np.pi * 5) / 12)
    notes = notes_from_contour(time, frequency, np.ones(len(time)), 4, onset_times=[1.5])
    assert len(notes) == 2
    assert [n.pitch for n in notes] == [69, 69]
    assert notes[0].start == pytest.approx(0.5, abs=0.01)
    assert notes[1].end == pytest.approx(2.5, abs=0.01)


def test_stable_decoder_rejects_short_jitter_and_keeps_real_changes_and_silence():
    times = np.arange(0, 3, 0.01)
    midi = np.where(times < 1, 69.0, 71.0)
    midi[30:32] = 70  # two-frame excursion is not an actual note
    frequency = 440 * 2 ** ((midi - 69) / 12)
    frequency[(times >= 1.5) & (times < 2)] = np.nan
    notes = stable_notes_from_contour(times, frequency, np.ones(len(times)), 3)
    assert [n.pitch for n in notes] == [69, 71, 71]
    assert notes[0].end == pytest.approx(1, abs=0.02)
    assert notes[2].start >= 1.98
    assert (
        stable_notes_from_contour(times, np.full(len(times), np.nan), np.zeros(len(times)), 3) == []
    )


def test_one_word_can_link_multiple_notes():
    times = np.arange(0, 2, 0.01)
    pitch = np.where(times < 1, 440, 493.883)
    notes = notes_from_contour(times, pitch, np.ones(len(times)), 2)
    melody = Melody(backend="test", notes=notes)
    lyrics = Lyrics(
        language="zh",
        timing_method="test",
        segments=[
            LyricLine(
                id="l",
                text="爱",
                start=0,
                end=2,
                words=[Word(id="w", text="爱", start=0, end=2)],
            )
        ],
    )
    link_words(melody, lyrics)
    assert len(notes) == 2
    assert all(n.lyric_word_ids == ["w"] for n in melody.notes)


def test_major_minor_templates_and_silence():
    c = np.zeros(12)
    c[[0, 4, 7]] = 1
    am = np.zeros(12)
    am[[9, 0, 4]] = 1
    assert classify_chroma(c)[0] == "C"
    assert classify_chroma(am)[0] == "Am"
    assert classify_chroma(np.zeros(12))[0] == "N"


@pytest.mark.parametrize("backend", ["stft", "cqt"])
def test_chords_on_audio_and_silence(tmp_path, backend):
    sr = 22050
    time = np.arange(4 * sr) / sr
    audio = sum(np.sin(2 * np.pi * f * time) for f in (261.6256, 329.6276, 391.9954)) * 0.08
    audio[-sr:] = 0
    path = tmp_path / "C_major.wav"
    sf.write(path, audio, sr)
    result = estimate_harmony(
        path,
        Rhythm(backend="test", bpm=120, beats=[0.5, 1, 1.5, 2, 2.5, 3, 3.5]),
        {"harmony_backend": backend},
    )
    assert result.chords[0].label == "C"
    assert result.chords[-1].label == "N"
    assert result.chords[-1].end == 4


@pytest.mark.parametrize("backend", ["librosa", "librosa_percussive"])
def test_beats_on_click_track(tmp_path, backend):
    sr = 22050
    audio = np.zeros(sr * 12)
    rng = np.random.default_rng(0)
    click = rng.normal(size=400) * np.exp(-np.arange(400) / 70)
    for time in np.arange(0.5, 11.5, 0.5):
        start = int(time * sr)
        audio[start : start + len(click)] += click * 0.2
    path = tmp_path / "clicks.wav"
    sf.write(path, audio, sr)
    result = estimate_rhythm(path, {"rhythm_backend": backend})
    assert result.bpm == pytest.approx(120, abs=4)
    assert len(result.beats) >= 18
    assert np.median(np.diff(result.beats)) == pytest.approx(0.5, abs=0.03)
