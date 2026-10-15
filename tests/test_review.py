from music_studio.backends.lyric_anchors import supplement_anchors
from music_studio.backends.lyric_phrasing import phrase_lyrics
from music_studio.review import line_identity, review_summary
from music_studio.schema import LyricLine, Lyrics, Word


def test_phrase_cuts_follow_pauses_keep_text_and_never_split_acoustic_units():
    line = LyricLine(
        id="l0",
        text="We walk through the night, and we will find our way home.",
        start=0,
        end=12,
        words=[
            Word(id=f"w{i}", text=t, start=s, end=s + 0.3)
            for i, (t, s) in enumerate(
                [
                    ("We", 0),
                    ("walk", 0.4),
                    ("through", 0.8),
                    ("the", 1.2),
                    ("night", 1.6),
                    ("and", 4),
                    ("we", 4.4),
                    ("will", 4.8),
                    ("find", 5.2),
                    ("our", 5.6),
                    ("way", 6),
                    ("home", 6.4),
                ]
            )
        ],
    )
    lyrics = Lyrics(language="en", timing_method="test", segments=[line])
    found = phrase_lyrics(lyrics)
    assert found.segments[0].text == "We walk through the night,"
    assert found.segments[1].text == "and we will find our way home."
    assert [w.model_dump() for s in found.segments for w in s.words] == [
        w.model_dump() for w in line.words
    ]
    assert " ".join(s.text for s in found.segments) == line.text


def test_dual_guide_only_fills_missing_spans_and_rejects_crossed_times():
    text = "one two three four"
    primary = Lyrics(
        language="en",
        timing_method="test",
        segments=[
            LyricLine(
                id="x",
                text=text,
                start=1,
                end=4,
                words=[
                    Word(id="a", text="one", start=1, end=1.4),
                    Word(id="b", text="three", start=3, end=3.4),
                ],
            )
        ],
    )
    secondary = Lyrics(
        language="en",
        timing_method="test",
        segments=[
            LyricLine(
                id="x",
                text=text,
                start=0,
                end=6,
                words=[
                    Word(id="a", text="one", start=0, end=0.5),
                    Word(id="b", text="two", start=2, end=2.4),
                    Word(id="c", text="four", start=2.5, end=2.9),
                ],
            )
        ],
    )
    found = supplement_anchors(primary, secondary)
    assert [(w.text, w.start) for w in found.segments[0].words] == [
        ("one", 1),
        ("two", 2),
        ("three", 3),
    ]
    assert primary.segments[0].words[0].start == 1


def test_phrase_without_acoustic_words_keeps_the_original_coarse_container():
    line = LyricLine(
        id="missing",
        text="We walk through the night. And we will find our way home.",
        start=60,
        end=120,
    )
    found = phrase_lyrics(Lyrics(language="en", timing_method="coarse", segments=[line]))
    assert len(found.segments) == 1
    assert found.segments[0].id == "missing"
    assert (found.segments[0].start, found.segments[0].end) == (60, 120)
    assert found.segments[0].text == line.text
    assert found.segments[0].words == []
    assert review_summary(found)["counts"]["timing"] == 1


def test_review_separates_missing_timing_from_text_and_invalidates_checked_text():
    line = LyricLine(
        id="x",
        text="hello world",
        start=0,
        end=2,
        words=[Word(id="w", text="hello", start=0.1, end=0.5)],
        review_reasons=["独立对齐未通过校验，保留原时间，请试听核对"],
    )
    lyrics = Lyrics(language="en", timing_method="test", segments=[line])
    found = review_summary(lyrics)
    assert found["lines"]["x"]["kinds"] == ["timing"]
    checked = {"x": line_identity(line)}
    assert review_summary(lyrics, checked)["counts"]["pending"] == 0
    line.text = "hello friend"
    assert review_summary(lyrics, checked)["counts"]["pending"] == 1
