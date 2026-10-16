# Music Studio Next: a local AI music production workstation

[中文](workbench-plan.md) · [Local model candidates](local-model-candidates.en.md) · Updated 2026-10-16

## Product and priorities

Build an open-source workstation for composition, arrangement, recording, audio/MIDI editing,
mixing and delivery, with a broad set of advanced local models.
**Build the production platform and its capabilities first, then integrate agents deeply.**
Beginner access comes from templates, presets, explanations and defaults. Experienced users
must still have tracks, instruments, effects, routing and automation.

This revision supersedes the earlier agent-first roadmap and its immediate focus on speech
cleanup and pause trimming. Existing adapters and cleanup remain useful; multitrack projects,
creation and mixing now drive development. Model results must enter one editable project.
A collection of disconnected model pages does not complete the platform.

## Preserve existing releases

Retain classic `main`, the published `v0.1.2`, and the Next `v0.2.0.dev2` prerelease.
Continue in the separate `codex/audio-workbench-next` worktree with isolated outputs and ports.
Do not automatically overwrite songs, analyses, corrected lyrics, caches or older projects.
Song analysis remains one workflow within the wider product.

## Platform scope

| Module | What users should be able to do | Project representation |
| --- | --- | --- |
| Multitrack arrangement | Place independent sources, move/split/duplicate/loop clips, snap, crossfade and audition ranges | Audio tracks, clips, source ranges, positions and a bar grid |
| Composition and MIDI | Write/import notes, chords and drums; quantize, transpose, edit velocity and change sounds | MIDI tracks, piano roll, drum grid, tempo/meter maps |
| Instruments and sampling | Use built-in instruments, samplers and libraries; later add third-party instruments | Instrument tracks, sound references and frozen audio |
| Recording | Record vocals/instruments with a metronome, count-in, takes and latency compensation | Source-preserving recordings, takes, device and monitoring settings |
| Mixing and mastering | Levels/pan, mute/solo, EQ, compression, reverb, delay, limiting, sidechain and automation | Inserts, buses, sends/returns, master output and envelopes |
| AI music creation | Generate from descriptions/lyrics, reinterpret references, add parts and regenerate ranges | New tracks/candidates, preserving original material and generation conditions |
| Separation and transcription | Extract vocals/instruments; transcribe melody, piano and multiple parts; analyze chords, beats and sections | Aligned stems, MIDI, chord tracks, tempo maps and markers |
| Singing and sound production | Synthesize singing from notes/lyrics, convert timbre, generate speech/effects | Lyric/note alignment, vocal tracks, effect clips and references |
| Restoration and transformation | Denoise, normalize, pitch/time shift, stretch and align music | Reversible effects/candidates; separate speech/music presets |
| Assets and delivery | Manage recordings, loops, one-shots, presets and models; find similar sounds and export | Asset library, model manager, mix/stem/MIDI/project exports |

These are target capabilities, not current support. See [model research](local-model-candidates.en.md).
Use a dependable audio engine for faders, EQ, routing and transport, and neural models for
generation, understanding, separation and conversion.

## Existing foundation and gaps

`0.2.0.dev2` provides provenance-aware assets, immutable processing candidates, a task queue,
audition/export, undo history, lyric correction, separation/transcription/melody tasks,
loudness inspection and speech cleanup. Reuse them. Ten capability entries include classical
algorithms and decoder variants, not ten distinct neural networks.

The earlier Next processing contract revolves around one source; the independent Create project now complements it:

- `MixTrack` in `studio/models.py` has no placement, source offset or duration; `Mix` permits eight inputs.
- Mixing in `studio/dsp.py` requires identical lengths, sample rates and channel counts.
- `LocalTaskRequest` expects one audio input. It cannot generate from an empty project or accept multiple audio/MIDI/lyric/reference conditions.
- Create provides multitrack playback, instrument tracks and basic note editing. Routing graphs, tempo maps and recording remain missing.

Create uses a new track/clip project and unified transport while retaining the earlier single-audio preview.

## Delivery order and acceptance

| Stage | Deliverable | Required evidence | Status |
| --- | --- | --- | --- |
| P0A Multitrack projects | Empty projects, audio tracks, clip placement/duration/source offsets, move/split/duplicate/loop, track removal, mute/solo/gain/pan, save/reopen and mix export | Place three sources of different lengths/rates at different positions; playback matches export; reopening preserves positions and provenance | First independent preview implemented; clip looping and other gaps remain; see [scope](create-preview.en.md) |
| P0B Creation and mixing foundation | MIDI piano roll, drum grid, basic instruments/sampler, BPM/meter, effects chains, buses/sends, automation, recording and device settings | Compose notes/drums, select sounds, record a track, add effects and mix; reopen and export audio/MIDI | Six sounds including three sampled instruments, eight grooves, MIDI import and note properties implemented; fixed-order EQ/compression/reverb and master limiting are now connected; recording/buses remain planned |
| P1 First music models | Rich task contracts and isolated workers; full-song/local generation, modern separation and music transcription | A real generation → separation → arrangement/instrument editing → mixing → export workflow; outputs enter the project | ACE-Step completed a real 12s instrumental; audition then adopt as a track. Modern separation/transcription and full creation acceptance remain incomplete |
| P2 Wider ecosystem | Singing, timbre conversion, effects/loop generation, semantic search, more generators/transcribers, time alignment and plugin compatibility | Reproducible examples and quality/resource/failure records per category; community providers share a contract | Planned |
| P3 Deep agent integration | Agents inspect projects and manipulate tracks, notes, effects and models through multistep workflows | UI and agents share commands/history; users can inspect, audition and undo actions | Deferred; existing adapters retained |

The first P0A production interface is implemented; see [scope and validation](create-preview.en.md). Continue P0B/P1 incrementally; test the first creation model
before every professional feature exists. Prioritize evaluating ACE-Step 1.5 for creation and
BSRoFormer/MelBand RoFormer for separation. Select exact weights, defaults and hardware profiles
from measurements; other providers use the same interface.

Continue the idea → draft → arrangement → mix → export workflow. The first EQ/compression/reverb, limiter and four presets are connected; see [mixing validation](mixing.en.md). Next prioritize modern separation, then clip repeat and a complete-piece acceptance run.

The first complete creation acceptance must produce a 30–60-second piece with retained stems,
MIDI, effect parameters, final mix and a reopenable project. A generated file, another model
button or a UI image alone does not satisfy that acceptance.

## Project and runtime architecture

Use `Project → Tracks → Clips`, with separate assets. Projects record sample rate, tempo/meter
maps, sections and revisions. Clips reference source assets/ranges and timeline positions;
MIDI retains notes/controllers. Define audio/musical time conversion: seconds are not MIDI ticks.
Version the project schema; provide migration, atomic saving, missing-asset recovery, backups
and crash recovery.

Use one transport and scheduler. Task refreshes must not recreate active audio sources;
fader/solo changes should respond immediately. Use peak caches, block reads and bounded memory.
Offline rendering and audition share project semantics, including tails, latency compensation,
resampling and clip boundaries.

Separate control, audio engine and GPU workers. The browser handles editing; low-latency
recording, device drivers and third-party plugins need a validated native host. Browser
playback is insufficient evidence. Compare reuse with implementation cost before choosing
the engine. Retain Python for projects, tasks and models; inference must not block callbacks.

The provider contract needs:

| Part | Required information |
| --- | --- |
| Description | Provider ID, capabilities, bilingual parameter schemas, version, maintenance status and separate code/weight licenses |
| Inputs | Zero or multiple inputs: audio, MIDI/score, lyrics, text, references, selections, BPM/key constraints; validate per capability |
| Execution | Isolated Python/native runtime, device/precision/quantization/offload, estimated and measured RAM/VRAM/disk, queue, progress and cancellation |
| Outputs | Typed audio/MIDI/score/annotation assets, time base, model/weight revision, seed, parameters and input hashes |
| Placement | New tracks/candidate clips at explicit positions with alignment/latency metadata; background completion must not overwrite ongoing edits |
| Extension | Community adapter documentation, a sample provider, contract checks and offline examples; explicit installation from verified sources |

Do not force every model into the current Torch/Transformers environment. Distinguish candidates,
installable providers, available dependencies, downloaded weights, successful inference and
measured quality. Show download sizes and removable caches. Measure CPU, 8GB, 12–16GB and 24GB+
profiles. The local 8GB GPU is the first target, not a ceiling on platform capability.

## Interface and beginner access

Center the interface on production: transport/record/BPM/meter above, assets/instruments/models
on the left, multitrack arrangement in the center, piano roll/drums/mixer below, and clip/effect/
generation inspectors on the right. Drag audio, MIDI and candidates into the arrangement.
Creation also works from an empty project.

Offer starting points for composing, recording and reworking music, auditionable sound/mixing
presets and example projects. Explain basic controls and progressively disclose advanced
parameters. Users can work directly and choose assistance when useful. Agents later operate
the same project through a sidebar. Localize menus, help, parameters, errors and documentation
in Chinese and English.

## Benchmarks and release gates

Retain the [benchmark protocol](benchmark-protocol.md), [melody report](melody-next.en.md)
and [speech report](speech-cleanup.en.md). Evaluate tasks separately; one leaderboard cannot
rank every model. Upstream results are not measurements on this machine.

| Category | Required evaluation |
| --- | --- |
| Projects/engine | Placement/loops, routing, mute/solo, undo/recovery, export round trips, realtime/offline agreement, memory and dropouts |
| Separation | Reference-based SDR/SI-SDR where appropriate, alignment, bleed, transient damage and per-case regressions; pin the checkpoint |
| Transcription/rhythm/chords | Onset/pitch/offset F1, octave errors, polyphony/instrument splits, beat/downbeat F1, weighted chord recall; pitch-class scores are not absolute-pitch accuracy |
| Music/effects generation | Frozen Chinese/English prompts, style/tempo/duration constraints, lyric CER/PER, blind listening, boundaries and reference melody preservation; retain seeds and full selection costs |
| Singing/voice/speech | Pronunciation, pitch/timing, identity/intelligibility, vibrato/slides and language coverage; similarity alone does not establish naturalness |
| Effects/restoration | Levels/true peak, distortion, tails, music preservation, clean controls, matched-loudness listening and failures |
| Every backend | Cold/warm time, peak RAM/VRAM, input duration, hardware/dependencies, offline operation, cancellation/recovery and distribution eligibility |

Defaults must satisfy quality, resources, licenses and maintenance. Advanced candidates, lighter
alternatives and older baselines can coexist. Cross-domain melody regressions still block
replacing the classic default; historical benchmarks do not limit platform scope. Accept
features against real projects and runtime records. This plan and upstream demos are not
delivered functionality.

