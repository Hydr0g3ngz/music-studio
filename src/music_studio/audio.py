from pathlib import Path

import numpy as np
import soundfile as sf

from .schema import AudioInfo

SAMPLE_RATE = 44100


def decode_audio(source: Path, destination: Path, digest: str) -> AudioInfo:
    """Decode once to float WAV. Analysis copies never change the master timebase."""
    import av

    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with av.open(str(source)) as container:
        if not container.streams.audio:
            raise ValueError("Input contains no audio stream")
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=SAMPLE_RATE)
        with sf.SoundFile(
            destination, mode="w", samplerate=SAMPLE_RATE, channels=2, subtype="FLOAT"
        ) as output:
            for frame in container.decode(audio=0):
                # The canonical timeline is decoded audio samples, not container timestamps.
                frame.pts = None
                for converted in resampler.resample(frame):
                    data = converted.to_ndarray().T
                    if not np.isfinite(data).all():
                        raise ValueError("Input contains non-finite audio samples")
                    output.write(data)
                    count += len(data)
            for converted in resampler.resample(None):
                data = converted.to_ndarray().T
                output.write(data)
                count += len(data)
    if count == 0:
        raise ValueError("Input is empty")
    return AudioInfo(
        source_name=source.name,
        source_sha256=digest,
        sample_rate=SAMPLE_RATE,
        channels=2,
        samples=count,
        duration=count / SAMPLE_RATE,
    )


def load_mono(path: Path, sample_rate: int) -> np.ndarray:
    import librosa

    audio, original_rate = sf.read(path, dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    if original_rate != sample_rate:
        mono = librosa.resample(mono, orig_sr=original_rate, target_sr=sample_rate)
    return mono.astype(np.float32)


def write_stem(path: Path, samples: np.ndarray, sample_rate: int, length: int) -> None:
    """Keep alignment and gain: float WAV avoids clipping or independent normalization."""
    if samples.ndim != 2 or not np.isfinite(samples).all():
        raise ValueError("Invalid stem waveform")
    if abs(len(samples) - length) > 2:
        raise ValueError("Separator changed audio length; refusing a misaligned stem")
    if len(samples) < length:
        samples = np.pad(samples, ((0, length - len(samples)), (0, 0)))
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, samples[:length], sample_rate, subtype="FLOAT")
