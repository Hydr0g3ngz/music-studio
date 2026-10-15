"""The on-disk contract: all times refer to the decoded source, never to a crop."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Interval(Record):
    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def positive_duration(self):
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class Word(Interval):
    id: str
    text: str
    score: float | None = Field(default=None, ge=0, le=1)


class LyricLine(Interval):
    id: str
    text: str
    words: list[Word] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def words_within_line(self):
        if any(w.start < self.start - 1e-6 or w.end > self.end + 1e-6 for w in self.words):
            raise ValueError("word is outside its lyric line")
        return self


class Lyrics(Record):
    language: str | None
    timing_method: str
    segments: list[LyricLine]
    warnings: list[str] = Field(default_factory=list)


class Note(Interval):
    id: str
    pitch: int = Field(ge=0, le=127)
    velocity: int = Field(default=90, ge=1, le=127)
    score: float = Field(ge=0, le=1)
    lyric_word_ids: list[str] = Field(default_factory=list)


class Melody(Record):
    backend: str
    notes: list[Note]
    pitch_file: str = "analysis/pitch.json"
    warnings: list[str] = Field(default_factory=list)


class Rhythm(Record):
    backend: str
    bpm: float | None = Field(default=None, gt=0)
    beats: list[float]
    downbeats: list[float] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ordered_beats(self):
        for values in (self.beats, self.downbeats):
            if any(t < 0 for t in values) or any(
                b <= a for a, b in zip(values, values[1:], strict=False)
            ):
                raise ValueError("beat times must be nonnegative and strictly increasing")
        return self


class Chord(Interval):
    label: str
    score: float = Field(ge=0, le=1)


class Harmony(Record):
    backend: str
    vocabulary: str = "major/minor/N"
    chords: list[Chord]
    warnings: list[str] = Field(default_factory=list)


class AudioInfo(Record):
    source_name: str
    source_sha256: str
    sample_rate: int = Field(gt=0)
    samples: int = Field(gt=0)
    channels: int = Field(ge=1, le=2)
    duration: float = Field(gt=0)

    @model_validator(mode="after")
    def consistent_duration(self):
        if abs(self.duration - self.samples / self.sample_rate) > 1e-6:
            raise ValueError("duration does not match sample count")
        return self


class Project(Record):
    schema_version: Literal["1.0"] = "1.0"
    generator: str = "music-studio-local/0.1.2"
    timebase: str = "seconds_from_decoded_audio_start"
    status: Literal["complete"] = "complete"
    audio: AudioInfo
    lyrics: Lyrics
    melody: Melody
    rhythm: Rhythm
    harmony: Harmony
    assets: dict[str, str]
    settings: dict
    stages: dict
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_timeline(self):
        duration = self.audio.duration
        intervals = [*self.lyrics.segments, *self.melody.notes, *self.harmony.chords]
        if any(item.end > duration + 1e-6 for item in intervals):
            raise ValueError("an annotation extends beyond the source audio")
        if any(t >= duration for t in self.rhythm.beats + self.rhythm.downbeats):
            raise ValueError("a beat extends beyond the source audio")
        words = [w for line in self.lyrics.segments for w in line.words]
        if len({line.id for line in self.lyrics.segments}) != len(self.lyrics.segments):
            raise ValueError("duplicate lyric line IDs")
        word_ids = {w.id for w in words}
        if len(word_ids) != len(words):
            raise ValueError("duplicate word IDs")
        if len({n.id for n in self.melody.notes}) != len(self.melody.notes):
            raise ValueError("duplicate note IDs")
        for note in self.melody.notes:
            if not set(note.lyric_word_ids) <= word_ids:
                raise ValueError("note references an unknown lyric word")
        return self
