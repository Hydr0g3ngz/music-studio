import csv
import unicodedata
from pathlib import Path

import mido

from .schema import Lyrics, Melody, Project, Rhythm


def link_words(melody: Melody, lyrics: Lyrics) -> None:
    words = [word for line in lyrics.segments for word in line.words]
    for note in melody.notes:
        note.lyric_word_ids = [
            word.id
            for word in words
            if min(note.end, word.end) - max(note.start, word.start) >= 0.02
        ]


def timestamp(seconds: float, *, srt: bool = False) -> str:
    # Round BEFORE splitting units so 59.9996 never becomes 00:59,1000.
    scale = 1000 if srt else 100
    total = max(0, round(seconds * scale))
    secs, fractional = divmod(total, scale)
    minutes, sec = divmod(secs, 60)
    if srt:
        hour, minute = divmod(minutes, 60)
        return f"{hour:02}:{minute:02}:{sec:02},{fractional:03}"
    return f"{minutes:02}:{sec:02}.{fractional:02}"


class MidiClock:
    """A tempo map that preserves seconds while following detected beat intervals."""

    ticks_per_beat = 960

    def __init__(self, rhythm: Rhythm):
        initial_bpm = rhythm.bpm or 120.0
        self.changes = [(0.0, mido.bpm2tempo(initial_bpm))]
        for left, right in zip(rhythm.beats, rhythm.beats[1:], strict=False):
            interval = right - left
            if 0.15 <= interval <= 3.0:
                self.changes.append((left, round(interval * 1_000_000)))
        self.changes = sorted(dict(self.changes).items())
        self.positions = [0.0]
        for (previous_time, tempo), (time, _) in zip(self.changes, self.changes[1:], strict=False):
            self.positions.append(
                self.positions[-1]
                + (time - previous_time) * 1_000_000 / tempo * self.ticks_per_beat
            )

    def tick(self, seconds: float) -> int:
        import bisect

        index = max(0, bisect.bisect_right([t for t, _ in self.changes], seconds) - 1)
        time, tempo = self.changes[index]
        return round(
            self.positions[index] + (seconds - time) * 1_000_000 / tempo * self.ticks_per_beat
        )


def write_midi(path: Path, melody: Melody, rhythm: Rhythm, lyrics: Lyrics) -> None:
    clock = MidiClock(rhythm)
    midi = mido.MidiFile(type=1, ticks_per_beat=clock.ticks_per_beat)
    timing = mido.MidiTrack()
    midi.tracks.append(timing)
    timing.append(mido.MetaMessage("track_name", name="Tempo map"))
    previous = 0
    for time, tempo in clock.changes:
        tick = clock.tick(time)
        timing.append(mido.MetaMessage("set_tempo", tempo=tempo, time=tick - previous))
        previous = tick
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Vocal melody"))
    track.append(mido.Message("program_change", program=0))
    events = []
    for note in melody.notes:
        start = clock.tick(note.start)
        end = max(start + 1, clock.tick(note.end))
        events.extend(
            [
                (start, 2, mido.Message("note_on", note=note.pitch, velocity=note.velocity)),
                (end, 0, mido.Message("note_off", note=note.pitch, velocity=0)),
            ]
        )
    # MIDI lyric text uses UTF-8; project JSON is the authoritative rich annotation.
    midi.charset = "utf-8"

    def text_key(text):
        return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())

    for line in lyrics.segments:
        complete_words = text_key("".join(word.text for word in line.words)) == text_key(line.text)
        if line.words and complete_words:
            for word in line.words:
                events.append(
                    (clock.tick(word.start), 1, mido.MetaMessage("lyrics", text=word.text))
                )
        elif line.text:
            # Corrected text has sentence timing only. Do not reuse obsolete word timings.
            events.append((clock.tick(line.start), 1, mido.MetaMessage("lyrics", text=line.text)))
    previous = 0
    for tick, _, message in sorted(events, key=lambda event: (event[0], event[1])):
        message.time = tick - previous
        track.append(message)
        previous = tick
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(path)


def export_project(project: Project, output: Path) -> None:
    folder = output / "exports"
    folder.mkdir(parents=True, exist_ok=True)
    write_midi(folder / "melody.mid", project.melody, project.rhythm, project.lyrics)
    lrc, srt = [], []
    for index, line in enumerate(project.lyrics.segments, 1):
        text = " ".join(line.text.splitlines())
        lrc.append(f"[{timestamp(line.start)}]{text}")
        srt.append(
            f"{index}\n{timestamp(line.start, srt=True)} --> "
            f"{timestamp(line.end, srt=True)}\n{text}\n"
        )
    (folder / "lyrics.lrc").write_text("\n".join(lrc) + ("\n" if lrc else ""), encoding="utf-8")
    (folder / "lyrics.srt").write_text("\n".join(srt), encoding="utf-8")
    with (folder / "chords.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["start_seconds", "end_seconds", "chord", "template_similarity"])
        for chord in project.harmony.chords:
            writer.writerow([chord.start, chord.end, chord.label, chord.score])
    with (folder / "beats.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["index", "time_seconds", "is_downbeat"])
        for index, time in enumerate(project.rhythm.beats):
            writer.writerow([index, time, int(time in project.rhythm.downbeats)])
