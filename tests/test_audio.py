import numpy as np
import pytest
import soundfile as sf

from music_studio.audio import decode_audio, write_stem
from music_studio.io import sha256


def test_decode_unicode_stereo_and_nonstandard_rate(tmp_path):
    source = tmp_path / "一首 歌.wav"
    rate = 48000
    t = np.arange(rate * 2) / rate
    sf.write(source, np.stack([np.sin(2 * np.pi * 440 * t) * 0.1, t * 0], axis=1), rate)
    dest = tmp_path / "output/source.wav"
    info = decode_audio(source, dest, sha256(source))
    audio, sr = sf.read(dest)
    assert sr == 44100
    assert audio.shape == (88200, 2)
    assert info.duration == 2
    assert np.max(np.abs(audio[:, 1])) == 0


def test_stems_preserve_gain_and_reject_drift(tmp_path):
    samples = np.ones((44100, 2), dtype=np.float32) * 1.3
    path = tmp_path / "stem.wav"
    write_stem(path, samples, 44100, 44100)
    data, _ = sf.read(path)
    assert np.max(data) == pytest.approx(1.3)
    with pytest.raises(ValueError, match="length"):
        write_stem(path, samples, 44100, 44200)
