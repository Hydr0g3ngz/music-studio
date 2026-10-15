"""Conservative timing transfer: only exact, monotonic acoustic anchors get word times."""

import unicodedata
from pathlib import Path

from ..io import read_json, sha256, write_json
from ..schema import LyricLine, Lyrics, Word
from .lyric_alignment import source_duration, tokens
from .lyric_phrasing import phrase_lyrics

GUIDES = {
    "small": "536b0662742c02347bc0e980a01041f333bce120",
    "large-v3-turbo": "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
}


def canonical(text):
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def exact_edit_matches(left, right):
    """Minimum-edit monotonic matching, allowing substitutions between exact anchors."""
    rows = [list(range(len(right) + 1))]
    for i, token in enumerate(left, 1):
        previous, row = rows[-1], [i] + [0] * len(right)
        for j, candidate in enumerate(right, 1):
            row[j] = min(previous[j] + 1, row[j - 1] + 1, previous[j - 1] + (token != candidate))
        rows.append(row)
    i, j, matches = len(left), len(right), []
    while i or j:
        if i and j and rows[i][j] == rows[i - 1][j - 1] + (left[i - 1] != right[j - 1]):
            if left[i - 1] == right[j - 1]:
                matches.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and rows[i][j] == rows[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    return matches[::-1]


def align_anchors(source: Path, lyrics: Lyrics, config: dict, *, preserve_lines=False) -> Lyrics:
    from .lyrics import transcribe_whisper

    if not lyrics.segments:
        return lyrics.model_copy(deep=True)
    if config.get("anchor_model") == "dual":
        first = align_anchors(
            source, lyrics, {**config, "anchor_model": "small"}, preserve_lines=True
        )
        extra = {**config, "anchor_model": "large-v3-turbo"}
        if config.get("_anchor_guide"):
            path = Path(config["_anchor_guide"])
            extra["_anchor_guide"] = str(path.with_name(path.stem + "-turbo.json"))
        second = align_anchors(source, lyrics, extra, preserve_lines=True)
        result = supplement_anchors(first, second)
        result.warnings.extend(second.warnings[-1:])
        return result if preserve_lines else phrase_lyrics(result)
    language = config.get("language") or lyrics.language
    guide_model = config.get("anchor_model", "small")
    revision = GUIDES[guide_model]
    identity = {
        "format": "whisper-small-guide-v1" if guide_model == "small" else "whisper-guide-v2",
        "audio_sha256": sha256(source),
        "language": language,
        "seed": config.get("seed", 0),
        "model_revision": revision,
    }
    cache = Path(config["_anchor_guide"]) if config.get("_anchor_guide") else None
    record = read_json(cache) if cache and cache.exists() else {}
    reused = all(record.get(k) == v for k, v in identity.items()) and "lyrics" in record
    if reused:
        guide = Lyrics.model_validate(record["lyrics"])
    else:
        guide = transcribe_whisper(
            source,
            {
                **config,
                "asr_model": guide_model,
                "asr_revision": revision,
                "asr_segmentation": "whole",
                "language": language,
                "_progress_label": "校准歌词时间",
            },
        )
        if cache:
            write_json(cache, {**identity, "lyrics": guide.model_dump()})
    result = transfer_anchors(lyrics, guide, source_duration(source), preserve_lines=preserve_lines)
    result.warnings.append(f"Acoustic guide: Whisper {guide_model}@{revision}; reused: {reused}.")
    return result


def transfer_anchors(lyrics: Lyrics, guide: Lyrics, duration: float, *, preserve_lines=False):
    """Pure timing ablation: no reference text, audio inference or mutable cache here."""
    phrases, groups = [], []
    for line in lyrics.segments:
        units = tokens(line.text)
        if not units:
            continue
        first_phrase = len(phrases)
        # Align whole recognition containers first. Display cuts must never discard
        # a multi-character acoustic token or change the transcript matching path.
        step = len(units)
        for index, start in enumerate(range(0, len(units), step)):
            begin = units[start][1] if start else 0
            end = units[start + step][1] if start + step < len(units) else len(line.text)
            phrases.append(
                LyricLine(
                    id=line.id if preserve_lines else f"{line.id}-p{index}",
                    text=line.text[begin:end].strip(),
                    start=line.start,
                    end=line.end,
                    review_reasons=[r for r in line.review_reasons if "识别分数" in r],
                )
            )
        groups.append((first_phrase, len(phrases), line.start, line.end))
    target, positions = [], []
    for index, line in enumerate(phrases):
        for value, start, end in tokens(line.text):
            target.append(canonical(value))
            positions.append((index, start, end))
    source_tokens, source_words, source_times = [], [], []
    for line in guide.segments:
        for word in line.words:
            units = tokens(word.text)
            begin = len(source_tokens)
            source_tokens.extend(canonical(item[0]) for item in units)
            source_times.extend((word.start, word.end) for _ in units)
            if units:
                source_words.append((begin, len(source_tokens), word))
    mapping, last_source = {}, -1
    # ASR chunks already locate text coarsely. Restrict repeated choruses to that
    # acoustic window instead of choosing a matching occurrence anywhere in the song.
    for first, last, left, right in groups:
        target_indices = [i for i, span in enumerate(positions) if first <= span[0] < last]
        source_indices = [
            i
            for i, (start, end) in enumerate(source_times)
            if i > last_source and end > left - 1 and start < right + 1
        ]
        matches = exact_edit_matches(
            [target[i] for i in target_indices], [source_tokens[i] for i in source_indices]
        )
        for target_index, guide_index in matches:
            source_index = source_indices[guide_index]
            mapping[source_index] = target_indices[target_index]
            last_source = max(last_source, source_index)
    assigned = [[] for _ in phrases]
    for begin, end, word in source_words:
        indices = [mapping.get(i) for i in range(begin, end)]
        if any(i is None for i in indices):
            continue
        if indices != list(range(indices[0], indices[0] + len(indices))):
            continue
        spans = [positions[i] for i in indices]
        if len({item[0] for item in spans}) != 1:
            continue
        phrase, start, _ = spans[0]
        end_char = spans[-1][2]
        assigned[phrase].append(
            (
                indices[0],
                Word(
                    id="pending",
                    text=phrases[phrase].text[start:end_char],
                    start=word.start,
                    end=word.end,
                ),
            )
        )
    count = 0
    for index, line in enumerate(phrases):
        line.words = [word for _, word in sorted(assigned[index], key=lambda pair: pair[0])]
        if line.words:
            line.start, line.end = min(w.start for w in line.words), max(w.end for w in line.words)
        else:
            prior = [word.end for items in assigned[:index] for _, word in items]
            later = [word.start for items in assigned[index + 1 :] for _, word in items]
            left, right = max(prior, default=0), min(later, default=duration)
            if right > left:
                line.start, line.end = left, right
        for word in line.words:
            word.id = f"w{count:05d}"
            count += 1
        covered = canonical("".join(word.text for word in line.words))
        if covered != canonical(line.text):
            line.review_reasons.append("部分字词尚无可靠时间，灰色文字按句定位")
    result = Lyrics(
        language=lyrics.language,
        timing_method="whisper_anchor_transfer",
        segments=phrases,
        warnings=lyrics.warnings
        + [
            "Exact monotonic text matches within native ASR windows (+/-1s) use "
            "Whisper acoustic word anchors. "
            "Unmatched words have no word timestamp; sentence ranges are estimates. "
            "This transfers anchors, not a forced alignment of unknown words."
        ],
    )
    return result if preserve_lines else phrase_lyrics(result)


def supplement_anchors(primary: Lyrics, secondary: Lyrics) -> Lyrics:
    """Only fill unlocated spans; retain every primary acoustic timestamp unchanged."""
    from .lyric_phrasing import timing_reasons

    result = primary.model_copy(deep=True)
    by_id = {line.id: line for line in secondary.segments}
    count = 0
    for line in result.segments:
        other = by_id.get(line.id)
        if other is None or line.text != other.text:
            raise ValueError("Acoustic anchor guides must use identical text and containers")

        def positions(words, text=line.text):
            out, cursor = [], 0
            for word in words:
                begin = text.find(word.text.strip(), cursor)
                if begin < 0:
                    raise ValueError("Acoustic word cannot be located in its original text")
                end = begin + len(word.text.strip())
                out.append((begin, end, word))
                cursor = end
            return out

        selected = positions(line.words)
        for begin, end, word in positions(other.words):
            if any(begin < b and end > a for a, b, _ in selected):
                continue
            before = [w for a, b, w in selected if b <= begin]
            after = [w for a, b, w in selected if a >= end]
            if before and word.start < before[-1].start:
                continue
            if after and word.end > after[0].end:
                continue
            selected.append((begin, end, word.model_copy(deep=True)))
            selected.sort(key=lambda item: item[0])
        line.words = [w for _, _, w in selected]
        if line.words:
            line.start = min(w.start for w in line.words)
            line.end = max(w.end for w in line.words)
        line.review_reasons = timing_reasons(line.text, line.words, line.review_reasons)
        for word in line.words:
            word.id = f"w{count:05d}"
            count += 1
    result.timing_method = "dual_whisper_anchor_transfer"
    result.warnings.append("Secondary acoustic matches only fill missing primary anchors.")
    return result
