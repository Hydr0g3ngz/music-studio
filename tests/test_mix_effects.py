"""DSP behavior and actual browser-kernel/export parity, not just schema tests."""

import io
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import sosfreqz

from music_studio.studio.effects import (
    Effects,
    Limiter,
    OutputLimiter,
    Rack,
    coefficients,
)

RATE = 44100
ROOT = Path(__file__).resolve().parents[1]


def test_eq_response_and_bypass():
    for kind, frequency in [("low", 20), ("mid", 1000), ("high", 16000)]:
        for db in (-12, 12):
            _, response = sosfreqz([coefficients(kind, db, RATE)], worN=[frequency], fs=RATE)
            assert abs(20 * np.log10(abs(response[0])) - db) < 0.2
    signal = np.random.default_rng(1).normal(0, 0.1, (5000, 2))
    np.testing.assert_array_equal(Rack(Effects()).process(signal), signal)
    settings = Effects.model_validate(
        {
            "bypass": True,
            "eq": {"enabled": True, "low_db": 12},
            "compressor": {"enabled": True},
            "reverb": {"enabled": True},
        }
    )
    np.testing.assert_array_equal(Rack(settings).process(signal), signal)


def test_compressor_steady_state_attack_release_and_stereo_link():
    settings = Effects.model_validate(
        {
            "compressor": {
                "enabled": True,
                "threshold_db": -20,
                "ratio": 4,
                "attack_ms": 10,
                "release_ms": 100,
            }
        }
    )
    signal = np.zeros((RATE * 2, 2))
    signal[:RATE] = [0.5, 0.1]
    signal[RATE:] = [0.01, 0.002]
    out = Rack(settings).process(signal)
    expected = 0.5 * 10 ** (-((20 * np.log10(0.5) + 20) * 0.75) / 20)
    np.testing.assert_allclose(out[RATE - 100 : RATE, 0], expected, atol=1e-6)
    np.testing.assert_allclose(out[:, 1], out[:, 0] / 5, atol=1e-12)
    assert out[0, 0] > out[1000, 0] > out[RATE - 1, 0]
    assert out[RATE + 100, 0] < out[-1, 0]
    assert out[-1, 0] == pytest.approx(0.01, abs=1e-9)


def test_limiter_ceiling_stereo_link_and_recovery():
    signal = np.tile([0.1, 0.025], (RATE, 1))
    signal[0] = [8, 2]
    limiter = OutputLimiter(Limiter(enabled=True, ceiling_db=-1, release_ms=50))
    out = limiter.process(signal)
    assert np.max(np.abs(out)) <= 10 ** (-1 / 20) + 1e-12
    np.testing.assert_allclose(out[:, 1], out[:, 0] / 4, atol=1e-12)
    assert out[1, 0] < out[-1, 0]
    assert out[-1, 0] == pytest.approx(0.1)
    np.testing.assert_array_equal(OutputLimiter(Limiter()).process(signal), signal)


def test_streaming_block_boundaries_tail_and_extreme_settings():
    settings = Effects.model_validate(
        {
            "eq": {"enabled": True, "low_db": 12, "mid_db": -12, "high_db": 12},
            "compressor": {"enabled": True, "attack_ms": 1, "release_ms": 20, "makeup_db": 12},
            "reverb": {"enabled": True, "mix": 0.5, "decay": 3},
        }
    )
    signal = np.zeros((RATE * 4, 2))
    signal[13] = [0.5, -0.25]
    full = Rack(settings).process(signal)
    rack = Rack(settings)
    split = np.concatenate([rack.process(signal[i : i + 137]) for i in range(0, len(signal), 137)])
    np.testing.assert_allclose(full, split, atol=1e-11)
    assert np.isfinite(full).all()
    assert np.max(abs(full[2000:RATE])) > 1e-5
    assert np.max(abs(full[-RATE // 10 :])) < 1e-4
    # Asymmetric reflections create a stereo space, not duplicated mono.
    assert not np.allclose(full[3000:10000, 0], -2 * full[3000:10000, 1])


@pytest.mark.parametrize("bypass", [False, True])
def test_javascript_audio_worklet_kernel_matches_python_export(bypass):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for cross-language DSP parity")
    settings = Effects.model_validate(
        {
            "bypass": bypass,
            "eq": {"enabled": True, "low_db": 3, "mid_db": -2, "high_db": 4},
            "compressor": {"enabled": True, "threshold_db": -24, "ratio": 4},
            "reverb": {"enabled": True, "mix": 0.32, "decay": 1.2},
        }
    )
    limiter = Limiter(enabled=True, ceiling_db=-3)
    signal = np.random.default_rng(42).normal(0, 0.4, (15000, 2))
    signal[3000:5000] = 0
    code = """
const fs = require('node:fs');
const { Rack, OutputLimiter } = require('./src/music_studio/ui/static/effects-dsp.js');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const rack = new Rack(input.settings), limiter = new OutputLimiter(input.limiter);
const left = [], right = [];
for (let start = 0; start < input.signal.length; start += 128) {
  const block = input.signal.slice(start, start + 128);
  const l = new Float64Array(block.length), r = new Float64Array(block.length);
  rack.process(block.map(x => x[0]), block.map(x => x[1]), l, r);
  limiter.process(l, r, l, r);
  left.push(...l); right.push(...r);
}
process.stdout.write(JSON.stringify(left.map((v, i) => [v, right[i]])));
"""
    result = subprocess.run(
        [node, "-e", code],
        cwd=ROOT,
        input=json.dumps(
            {
                "settings": settings.model_dump(),
                "limiter": limiter.model_dump(),
                "signal": signal.tolist(),
            }
        ),
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    actual = np.array(json.loads(result.stdout))
    expected = OutputLimiter(limiter).process(Rack(settings).process(signal))
    np.testing.assert_allclose(actual, expected, atol=2e-10, rtol=2e-10)


def test_effects_save_undo_validation_and_real_export(client):
    # Reuse the ordinary arrangement API, source audio remains immutable.
    state = client.post("/api/workstation/projects", json={"title": "FX check"}).json()
    prefix = f"/api/workstation/projects/{state['id']}"
    data = io.BytesIO()
    signal = np.full((RATE // 5, 2), [0.8, 0.4])
    sf.write(data, signal, RATE, format="WAV", subtype="FLOAT")
    state = client.post(
        prefix + "/import?revision=0",
        files={
            "file": ("test.wav", data.getvalue()),
        },
    ).json()
    original = client.get(prefix + "/audio/" + state["assets"][0]["id"]).content
    state["content"]["master_db"] = 6
    state["content"]["tracks"][0]["effects"] = {
        "reverb": {"enabled": True, "mix": 0.2, "decay": 0.6},
    }
    state["content"]["limiter"] = {"enabled": True, "ceiling_db": -2}
    updated = client.put(prefix, json={"revision": state["revision"], "content": state["content"]})
    assert updated.status_code == 200, updated.text
    updated = updated.json()
    exported = client.post(prefix + "/export/wav", json={"revision": updated["revision"]})
    assert exported.status_code == 200, exported.text
    audio, rate = sf.read(io.BytesIO(client.get(exported.json()["url"]).content))
    assert len(audio) == round((0.2 + 0.6 + 0.1) * rate)
    assert np.max(abs(audio)) <= 10 ** (-2 / 20) + 2e-7
    assert np.max(abs(audio[RATE // 5 :])) > 0.001
    undone = client.post(prefix + "/history/undo", json={"revision": updated["revision"]}).json()
    assert not undone["content"]["limiter"]["enabled"]
    redone = client.post(prefix + "/history/redo", json={"revision": undone["revision"]}).json()
    assert redone["content"] == updated["content"]
    assert (
        client.put(
            prefix, json={"revision": state["revision"], "content": state["content"]}
        ).status_code
        == 409
    )
    redone["content"]["tracks"][0]["effects"]["reverb"]["decay"] = 100
    assert (
        client.put(
            prefix, json={"revision": redone["revision"], "content": redone["content"]}
        ).status_code
        == 422
    )
    assert client.get(prefix + "/audio/" + state["assets"][0]["id"]).content == original


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from music_studio.ui.server import create_app

    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1") as app:
        yield app
