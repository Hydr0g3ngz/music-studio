"""Display phrases from punctuation and acoustic pauses; never invent word timings."""

import re

from ..schema import LyricLine, Lyrics
from .lyric_alignment import tokens

_DANGLING = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "to",
    "of",
    "in",
    "with",
    "for",
    "at",
    "from",
    "my",
    "your",
    "our",
    "their",
    "i",
    "we",
    "you",
    "he",
    "she",
    "they",
    "i'll",
    "we'll",
}


def _coverage(text):
    return "".join(c.casefold() for c in text if c.isalnum())


def timing_reasons(text, words, reasons):
    # Recompute per display phrase, rather than inheriting a minute-wide warning.
    kept = [r for r in reasons if not any(s in r for s in ("时间", "定位", "对齐"))]
    if _coverage(text) != _coverage("".join(w.text for w in words)):
        kept.append("部分字词尚无可靠时间，灰色文字按句定位")
    return kept


def phrase_lyrics(lyrics: Lyrics) -> Lyrics:
    """Keep all text and acoustic spans, with stable IDs within the new result version."""
    result = lyrics.model_copy(deep=True)
    output = []
    for line in result.segments:
        units = tokens(line.text)
        if len(units) < 5 or not line.words:
            line.review_reasons = timing_reasons(line.text, line.words, line.review_reasons)
            output.append(line)
            continue
        spans, cursor = [], 0
        for word in line.words:
            text = word.text.strip()
            start = line.text.find(text, cursor)
            if start < 0 or not text:
                continue
            spans.append((start, start + len(text), word))
            cursor = start + len(text)
        boundaries, left = [], 0
        while len(units) - left > 4:
            candidates = []
            for index in range(left + 3, min(len(units), left + 22)):
                cut = units[index][1]
                if any(a < cut < b for a, b, _ in spans):
                    continue
                previous = [w for a, b, w in spans if b <= cut]
                following = [w for a, b, w in spans if a >= cut]
                gap = following[0].start - previous[-1].end if previous and following else 0
                between = line.text[units[index - 1][2] : cut]
                punctuation = bool(re.search(r"[.!?。！？;；\n]", between))
                comma = bool(re.search(r"[,，]", between))
                natural = punctuation or gap >= 0.45 or (comma and index - left >= 5)
                if natural:
                    # Prefer an early actual phrase boundary over a fixed word count.
                    candidates.append((index, cut))
            if candidates:
                index, cut = candidates[0]
            elif len(units) - left > 22:
                choices = [
                    (index, units[index][1])
                    for index in range(left + 10, left + 21)
                    if units[index - 1][0].casefold() not in _DANGLING
                    and not any(a < units[index][1] < b for a, b, _ in spans)
                ]
                if not choices:
                    break
                index, cut = min(choices, key=lambda x: abs(x[0] - left - 16))
            else:
                break
            boundaries.append(cut)
            left = index
        if not boundaries:
            line.review_reasons = timing_reasons(line.text, line.words, line.review_reasons)
            output.append(line)
            continue
        cuts = [0, *boundaries, len(line.text)]
        for i, (begin, end) in enumerate(zip(cuts, cuts[1:], strict=False)):
            words = [w for a, b, w in spans if a >= begin and b <= end]
            previous = [w.end for a, b, w in spans if b <= begin]
            following = [w.start for a, b, w in spans if a >= end]
            start = min((w.start for w in words), default=max(previous, default=line.start))
            stop = max((w.end for w in words), default=min(following, default=line.end))
            if stop <= start:
                start, stop = line.start, line.end
            output.append(
                LyricLine(
                    id=f"{line.id}-p{i}",
                    text=line.text[begin:end].strip(),
                    start=start,
                    end=stop,
                    words=words,
                    review_reasons=timing_reasons(line.text[begin:end], words, line.review_reasons),
                )
            )
    result.segments = output
    return result
