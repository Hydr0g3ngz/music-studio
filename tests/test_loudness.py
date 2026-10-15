import json

import numpy as np
import pytest
import soundfile as sf

from music_studio.io import sha256
from music_studio.studio import dsp
from music_studio.studio.cleanup import resample_channel
from music_studio.studio.loudness import measure
from music_studio.studio.models import LoudnessNormalize


def test_calibrated_loudness_gain_channels_and_true_peak(tmp_path):
    rate = 48000
    sine = 0.1 * np.sin(2 * np.pi * 1000 * np.arange(rate * 4) / rate)
    mono, stereo, quiet = [tmp_path / name for name in ("mono.wav", "stereo.wav", "quiet.wav")]
    sf.write(mono, sine, rate, subtype="FLOAT")
    sf.write(stereo, np.column_stack([sine, sine]), rate, subtype="FLOAT")
    sf.write(quiet, sine / 2, rate, subtype="FLOAT")
    a, b, c = map(measure, [mono, stereo, quiet])
    assert a["integrated_lufs"] == pytest.approx(-23.0, abs=0.1)
    assert b["integrated_lufs"] - a["integrated_lufs"] == pytest.approx(3.0103, abs=0.1)
    assert c["integrated_lufs"] - a["integrated_lufs"] == pytest.approx(-6.0206, abs=0.1)
    assert a["true_peak_dbtp"] == pytest.approx(-20.0, abs=0.1)
    assert not a["loudness_range_stable"]


def test_silence_short_clips_and_nonfinite_samples(tmp_path):
    path = tmp_path / "short.wav"
    sf.write(path, np.zeros(100), 44100, subtype="FLOAT")
    result = measure(path)
    assert result["integrated_lufs"] is None and result["true_peak_dbtp"] is None
    assert result["unmeasurable_reason"] == "shorter_than_400ms"
    json.dumps(result, allow_nan=False)
    with pytest.raises(ValueError, match="Cannot normalize"):
        dsp.process(path, tmp_path / "out.wav", LoudnessNormalize(), {})
    sf.write(path, np.array([np.nan]), 44100, subtype="FLOAT")
    with pytest.raises(ValueError, match="non-finite"):
        measure(path)


def test_intersample_peaks_and_gate_are_distinct_from_pcm_peak_and_rms(tmp_path):
    path = tmp_path / "intersample.wav"
    rate = 48000
    t = np.arange(rate * 4) / rate
    signal = 0.5 * np.sin(2 * np.pi * 12000 * t + np.pi / 4)
    signal *= np.minimum(1, t / 0.02) * np.minimum(1, (4 - t) / 0.02)
    sf.write(path, signal, rate, subtype="FLOAT")
    levels = measure(path)
    assert levels["sample_peak_dbfs"] == pytest.approx(-9.0309, abs=0.01)
    assert levels["true_peak_dbtp"] == pytest.approx(-6.0206, abs=0.15)
    # Quiet trailing material must not dilute the integrated result like RMS.
    t = np.arange(rate * 20) / rate
    tone = 0.1 * np.sin(2 * np.pi * 1000 * t)
    sf.write(path, np.concatenate([tone, np.zeros_like(tone)]), rate, subtype="FLOAT")
    assert measure(path)["integrated_lufs"] == pytest.approx(-23.0, abs=0.15)


def test_normalization_reaches_target_and_preserves_source(tmp_path):
    source, output = tmp_path / "source.wav", tmp_path / "normalized.wav"
    t = np.arange(48000 * 4) / 48000
    sf.write(
        source, np.column_stack([0.03 * np.sin(2 * np.pi * 1000 * t)] * 2), 48000, subtype="FLOAT"
    )
    original = sha256(source)
    report = dsp.process(source, output, LoudnessNormalize(target_lufs=-16), {})
    assert report["loudness"]["after"]["integrated_lufs"] == pytest.approx(-16, abs=0.1)
    assert report["loudness"]["after"]["true_peak_dbtp"] <= -1
    assert not report["loudness"]["peak_limited"]
    assert sha256(source) == original
    assert sf.info(source).frames == sf.info(output).frames


def test_normalization_respects_true_peak_instead_of_clipping(tmp_path):
    source, output = tmp_path / "peaky.wav", tmp_path / "bounded.wav"
    t = np.arange(48000 * 4) / 48000
    signal = 0.002 * np.sin(2 * np.pi * 1000 * t)
    signal[48000] = 0.99
    sf.write(source, signal, 48000, subtype="FLOAT")
    report = dsp.process(source, output, LoudnessNormalize(target_lufs=-16), {})
    assert report["loudness"]["peak_limited"]
    assert report["loudness"]["after"]["integrated_lufs"] < -16.2
    assert report["loudness"]["after"]["true_peak_dbtp"] <= -1


def test_resampling_preserves_short_tail_and_impulse_time():
    for length in [1, 100, 44101]:
        data = np.zeros(length, dtype=np.float32)
        data[min(length - 1, 22050)] = 0.25
        mono = resample_channel(data, 44100, 16000)
        result = resample_channel(mono, 16000, 44100, length)
        assert len(result) == length and np.isfinite(result).all()
        if length > 22050:
            assert abs(int(np.argmax(np.abs(result))) - 22050) <= 1
