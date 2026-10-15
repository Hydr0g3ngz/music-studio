"""Selective re-recognition; unselected corrected lines stay exactly as supplied."""

from pathlib import Path

import soundfile as sf

from ..audio import load_mono
from ..schema import Lyrics
from .lyrics import transcribe


def retry_line(source: Path, lyrics: Lyrics, line_id: str, output: Path, config: dict) -> Lyrics:
    index = next((i for i, line in enumerate(lyrics.segments) if line.id == line_id), None)
    if index is None:
        raise ValueError("要重新识别的歌词句不存在")
    selected = lyrics.segments[index]
    audio = load_mono(source, 16000)
    left = max(0, selected.start - 0.25)
    right = min(len(audio) / 16000, selected.end + 0.25)
    path = output / "analysis/retry-audio.wav"
    sf.write(path, audio[round(left * 16000) : round(right * 16000)], 16000, subtype="FLOAT")
    found = transcribe(path, config)
    if not found.segments:
        raise ValueError("这一句未识别到可用歌词，之前的结果已保留。可切换音源或直接改字。")
    result = lyrics.model_copy(deep=True)
    replacement = []
    occupied = {line.id for i, line in enumerate(lyrics.segments) if i != index}
    for i, line in enumerate(found.segments):
        line.id = selected.id if i == 0 else f"{selected.id[:50]}-r{i}"
        base_id, suffix = line.id, 2
        while line.id in occupied:
            line.id = f"{base_id}-{suffix}"
            suffix += 1
        occupied.add(line.id)
        line.start += left
        line.end = min(right, line.end + left)
        for word in line.words:
            word.start += left
            word.end = min(right, word.end + left)
        replacement.append(line)
    result.segments[index : index + 1] = replacement
    count = 0
    for line in result.segments:
        for word in line.words:
            word.id = f"w{count:05d}"
            count += 1
    result.timing_method = "selective_retry/" + found.timing_method
    result.warnings.extend(found.warnings)
    result.warnings.append(
        "Only the requested sentence was re-recognized; other corrections retained."
    )
    return Lyrics.model_validate(result.model_dump())
