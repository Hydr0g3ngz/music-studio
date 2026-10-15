# Music Studio Next: audio workbench plan

[中文](workbench-plan.md) · 2026-10-16

Build a local workbench for music, speech, field recordings and sound assets. Beginners work
through concrete goals; experienced users can inspect parameters. Every operation should be
auditionable, comparable, reversible and exportable.

The clarified core is **local open-source audio AI + agent tools + a beginner-friendly
workbench**. Codex is the first agent integration. Agent and UI must share the same
selection, task, candidate, history and export state. Register actual runtime, memory,
license and offline requirements; do not assume every open model fits an 8GB GPU.

Expose the typed local service through MCP for existing Codex clients, and use the
official app-server protocol for embedded conversations, tool events and auditionable
candidates. Both adapters share the same operation service rather than arbitrary shell
commands. Validate the installed protocol schema and real tool/UI synchronization.
Sources: [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli),
[Codex App Server](https://learn.chatgpt.com/docs/app-server).

## Preserve the current product

Keep `main` and the published `v0.1.2` separate from `codex/audio-workbench-next`.
Development uses a separate managed worktree, output folder and port. Do not automatically
migrate or overwrite existing recordings, analysis versions, corrections or cached models.
The song-analysis and sing-along workflows remain available. KTV is not the new product focus.

## Delivery and evidence

| Stage | Outcome | Evidence needed | Status |
| --- | --- | --- | --- |
| 0 | Stable-version preservation | Tag, branch, separate checkout/output/port | Separate checkout/output/8900 verified; clean stable main and 8775 retained |
| 1A | Shared agent/UI foundation | Typed tools, common state, events, model registry; real MCP and Codex/UI flow | 16 tools including A/B; model catalog, isolated checks, durable queue and assets; real MCP/Codex verified |
| 1 | Better melody and MIDI | Paired note/frame benchmarks, octave/voicing errors, resources, MIDI round trips and vocal/note A/B | GTS/vocadito model and rest-decoder comparisons complete; MIDI/synthesis available; cross-domain regressions block promotion; segmentation work continues |
| 2 | Useful without models | Import, audition, precise range, trim, fades, mixer, undo/redo, rendered export; real-file and browser checks | Clean no-model wheel, import, trash/restore, history and continuous playback verified; checks in preview guide |
| 3 | Modular analysis | Run separation, transcription, notes, rhythm and audio inspection independently | Ten capability entries; LUFS/true peak and two CPU denoisers added; 32 paired speech regression cases with failures retained |
| 4 | Accessible tasks and cleanup | Concrete tasks and advanced controls share the same reversible state | Speech cleanup, loudness, synchronized matched A/B and explicit setup available; broader recording/language validation, long audio and batching remain |
| 5 | Assets and recipes | Tags, bookmarks, backups, recipes, batch jobs, model management and recovery | Planned |
| 6 | Semantic/generative experiments | Search, text-conditioned separation and local rewriting, with measured costs and explicit provenance | Planned |

Documentation or an isolated prototype does not complete the workbench objective. Record
actual commands, checks and UI evidence before marking an item delivered.

The `0.2.0.dev2` [speech report](speech-cleanup.en.md) retains frozen pilot/follow-up lists,
objective metrics, clean controls and regressions. Next priorities are bounded memory and
chunking for long recordings, inspectable pause trimming, then semantic search and
text-conditioned separation using the same asset/audition system. Chinese and real-world
recordings need independent reference evaluation; two English speakers do not establish
generalization. Cross-domain melody regressions still block replacing the classic default.

## Melody investigation

The existing GTSinger report shows inadequate note-level accuracy. Separate pitch estimation,
note boundaries, MIDI serialization and synthesis timbre. Assess repeated notes, consonant gaps,
octave errors, breathy vocals, rests, timing drift and note-off ordering. A nicer instrument does
not prove better transcription.

Compare [ROSVOT](https://github.com/RickyL-2000/ROSVOT) and
[Basic Pitch](https://github.com/spotify/basic-pitch) against the frozen 12-case GTSinger baseline.
Add independent [vocadito](https://zenodo.org/records/5578807) note/f0 annotations, reporting
annotator differences, training overlap and domain limits. Commercial uploads are functional
and listening checks, not accuracy tests without ground truth. Default selection must consider
onset/pitch and offset F1, voicing, octave errors, resources and per-case regressions.

## Interaction and architecture

Maintain a provenance-aware asset library, a shared timeline and selection, an inspector,
reversible edits separate from recognition revisions, conflict checks and matching preview/export.
Do not reload audio when task status changes. Keep bilingual UI, legacy workflows, existing
export formats, offline processing and an account-free basic workflow.

Potential directions: an audio microscope that explains harshness; erase a described sound;
turn humming into an instrumental sketch; semantic search over private local assets; podcast
intro recipes with ducking; loudness-matched parallel treatments; rewrite only a selected range;
map sound events through long recordings; translate plain-language instructions into a visible
operation list. These are future capabilities, not decorative buttons that pretend to work.

Study [Waveform Playlist](https://github.com/naomiaro/waveform-playlist) and
[Audacity](https://github.com/audacity/audacity) for editing interaction;
[DeepFilterNet](https://github.com/Rikorose/DeepFilterNet) for speech enhancement;
[AudioSep](https://github.com/Audio-AGI/AudioSep) for described-sound separation; and
[ACE-Step](https://github.com/ace-step/ACE-Step-1.5) for local generative editing.
Validate licensing, resources, failure cases and quality before integration. Do not silently
download new models into the stable application. Primary GPU target remains an 8GB RTX 4070 Laptop.
