"""Experimental audio-only ROSVOT adapter; upstream remains a pinned external checkout.

Uses the author's ROSVOT + RWBD + RMVPE checkpoints and inference defaults.
Reference text, note times and word boundaries never enter this adapter.

Based on Ruiqi Li's ROSVOT inference (2024), MIT; see docs/licenses/ROSVOT-MIT.txt.
"""

import math
import sys
from pathlib import Path

import numpy as np


class RosvotModel:
    def __init__(self, upstream: Path, checkpoints: Path, device: str = "cuda"):
        import torch
        import yaml

        sys.path.insert(0, str(upstream.resolve()))
        from modules.pe.rmvpe.constants import (
            MEL_FMAX,
            MEL_FMIN,
            N_MELS,
            SAMPLE_RATE,
            WINDOW_LENGTH,
        )
        from modules.pe.rmvpe.inference import RMVPE
        from modules.pe.rmvpe.model import E2E0
        from modules.pe.rmvpe.spec import MelSpectrogram
        from modules.rosvot.rosvot import MidiExtractor, WordbdExtractor
        from utils.audio.mel import MelNet

        self.device = torch.device(device)
        self.params = yaml.safe_load(
            (checkpoints / "rosvot/config.yaml").read_text(encoding="utf-8")
        )
        self.params.update(note_bd_threshold=0.85, max_frames=30000)
        word_params = yaml.safe_load((checkpoints / "rwbd/config.yaml").read_text(encoding="utf-8"))
        word_params.update(word_bd_threshold=0.5, max_frames=30000)
        self.model = MidiExtractor(self.params).eval().to(self.device)
        self.word_model = WordbdExtractor(word_params).eval().to(self.device)
        for kind, model in (("rosvot", self.model), ("rwbd", self.word_model)):
            checkpoint = torch.load(
                checkpoints / kind / "model.pt", map_location="cpu", weights_only=True
            )
            model.load_state_dict(checkpoint["state_dict"]["model"], strict=True)
        self.word_mel_bins = word_params["use_mel_bins"]
        self.mel = MelNet(self.params)
        self.mel.to(self.device)
        # Construct the official RMVPE object with a restricted checkpoint loader.
        self.pitch = RMVPE.__new__(RMVPE)
        self.pitch.device = self.device
        self.pitch.resample_kernel = {}
        self.pitch.hop_length = 160
        self.pitch.model = E2E0(4, 1, (2, 2)).eval().to(self.device)
        checkpoint = torch.load(
            checkpoints / "rmvpe/model.pt", map_location="cpu", weights_only=True
        )
        self.pitch.model.load_state_dict(checkpoint["model"], strict=True)
        self.pitch.mel_extractor = MelSpectrogram(
            N_MELS, SAMPLE_RATE, WINDOW_LENGTH, 160, None, MEL_FMIN, MEL_FMAX
        ).to(self.device)

    def predict(self, source: Path, output: Path):
        import librosa
        import torch
        from utils.audio.pitch_utils import (
            boundary2Interval,
            denorm_f0,
            f0_to_coarse,
            norm_interp_f0,
        )
        from utils.commons.dataset_utils import pad_or_cut_xd

        from music_studio.schema import Melody, Note

        rate, hop = self.params["audio_sample_rate"], self.params["hop_size"]
        audio, _ = librosa.load(source, sr=rate, mono=True)
        duration = len(audio) / rate
        real_length = math.ceil(len(audio) / hop)
        if real_length > 30000:
            raise ValueError("Experimental unchunked ROSVOT input exceeds 30000 frames")
        length = (
            math.ceil(real_length / self.params["frames_multiple"]) * self.params["frames_multiple"]
        )
        with torch.inference_mode():
            f0s, _ = self.pitch.get_pitch_batch(
                [audio],
                sample_rate=rate,
                hop_size=hop,
                lengths=[real_length],
                fmin=self.params["f0_min"],
                fmax=self.params["f0_max"],
            )
            f0, uv = norm_interp_f0(f0s[0])
            f0 = pad_or_cut_xd(torch.as_tensor(f0).float(), length, 0)
            uv = pad_or_cut_xd(torch.as_tensor(uv).float(), length, 0)
            pitch = f0_to_coarse(denorm_f0(f0, uv))[None].to(self.device)
            uv = uv[None].long().to(self.device)
            mel = pad_or_cut_xd(self.mel(torch.from_numpy(audio)[None].to(self.device)), length, 1)
            mel[:, real_length:] = 0
            mask = mel.abs().sum(-1) > 0
            word = self.word_model(
                mel=mel[:, :, : self.word_mel_bins],
                pitch=pitch,
                uv=uv,
                non_padding=mask,
                train=False,
            )["word_bd_pred"]
            result = self.model(
                mel=mel[:, :, : self.params["use_mel_bins"]],
                word_bd=word,
                pitch=pitch,
                uv=uv,
                non_padding=mask,
                train=False,
            )
            boundaries = result["note_bd_pred"][0, :real_length].cpu().numpy()
            count = int(result["note_lengths"][0])
            pitches = result["note_pred"][0, :count].cpu().numpy()
            intervals = boundary2Interval(boundaries) * hop / rate
        np.savez_compressed(
            output / "activations.npz",
            f0=f0s[0],
            boundaries=boundaries,
            pitches=pitches,
            intervals=intervals,
        )
        if len(intervals) != len(pitches):
            raise ValueError("ROSVOT boundary and pitch counts differ")
        notes = []
        for pitch, (start, end) in zip(pitches, intervals, strict=True):
            start, end = max(0, float(start)), min(duration, float(end))
            if pitch > 0 and end > start:
                notes.append(
                    Note(
                        id=f"n{len(notes):05d}",
                        start=start,
                        end=end,
                        pitch=int(pitch),
                        score=1,
                        velocity=90,
                    )
                )
        return Melody(
            backend="rosvot/rwbd/audio-only/official-defaults",
            notes=notes,
            warnings=[
                "Experimental model. Note scores are placeholders, not calibrated confidence."
            ],
        )
