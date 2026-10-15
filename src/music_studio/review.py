"""Explain review hints without treating missing timing as a transcription error."""

import unicodedata

from .io import fingerprint


def text_key(value):
    return "".join(c for c in unicodedata.normalize("NFKC", value).casefold() if c.isalnum())


def line_identity(line):
    return fingerprint(
        {
            "text": line.text,
            "start": line.start,
            "end": line.end,
            "words": [(w.text, w.start, w.end) for w in line.words],
        }
    )


def review_summary(lyrics, reviewed=None, corrected=None):
    reviewed, corrected = reviewed or {}, corrected or {}
    result, counts = {}, {"text": 0, "timing": 0, "pending": 0, "reviewed": 0}
    for line in lyrics.segments:
        text_reasons = [r for r in line.review_reasons if "识别分数" in r or "识别分歧" in r]
        if line.id in corrected:
            text_reasons = []
        missing_time = text_key(line.text) != text_key("".join(w.text for w in line.words))
        kinds = (["text"] if text_reasons else []) + (["timing"] if missing_time else [])
        checked = reviewed.get(line.id) == line_identity(line)
        result[line.id] = {
            "kinds": kinds,
            "text_reasons": text_reasons,
            "reviewed": checked,
            "identity": line_identity(line),
        }
        counts["text"] += bool(text_reasons)
        counts["timing"] += missing_time
        counts["reviewed"] += checked
        counts["pending"] += bool(kinds) and not checked
    return {
        "lines": result,
        "counts": counts,
        "note": "提示用于安排试听，不是错误判定；缺少词时间不代表文字错误。",
    }
