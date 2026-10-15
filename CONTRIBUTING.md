# Contributing

[中文](CONTRIBUTING.zh-CN.md) · [Roadmap](docs/roadmap.en.md)

Use Python 3.11 or 3.12. Core/API/UI development needs no neural runtime:

```sh
python -m pip install -e ".[ui,benchmark,dev]"
python -m ruff check .
python -m pytest -q
node --test tests/ui_playback.test.cjs tests/ui_i18n.test.cjs
python scripts/package_release.py
```

Core and UI tests do not download neural models and can run with `.[ui,dev]` alone. They cover sample-rate conversion, note timing, one-word/multiple-note mapping, major/minor chord baselines, beat detection, variable-tempo MIDI, cache invalidation, resume after a stage failure, upload/result/download flows, cancellation and project path boundaries. Pipeline orchestration tests use deterministic adapters; they are not model-accuracy tests.

Install `.[benchmark]` as well to exercise the optional music-metric adapter test. CI includes this extra. The [public regression suite](benchmarks/README.md) is an opt-in real-audio check with frozen upstream references; downloading it and running neural inference are separate commands. Never commit benchmark audio, reference lyric text or recognition transcripts. The explicitly credited bundled preview is a separate CC BY 3.0 presentation asset, not benchmark data. Report training overlap and timing coverage beside accuracy.

The UI is served by `music-studio ui`. HTML, CSS and JavaScript live in `src/music_studio/ui/static/` and need no frontend build or external CDN. After changing static assets, reload the browser and check the upload, playback, lyric seek and export flows. Keep the audio tracks on one Web Audio clock. The UI should consume the engine's project records rather than add a second implementation of inference.

Playback regression tests use Node's built-in runner (Node 22 recommended), without npm dependencies. They exercise the actual status poll handler and audio-session code, including legacy version identity, concurrent loading, lazy stems, cancelled requests and rapid seek. Always verify continuous real-browser playback as well; a passing fake AudioContext test cannot establish audible quality.

Scoped contribution ideas and acceptance criteria are listed in the [roadmap](docs/roadmap.md). Do not add a full notation editor to solve lyric-text correction. For benchmark changes, keep frozen manifests and confirmation assignments intact, account for failures, separate languages/domains, and publish timing coverage beside conditional timing error.

Before changing inference adapters, also run `scripts/smoke_test.py` on local audio with real models and run `music-studio validate OUTPUT`. Report the hardware, package versions, model settings and resulting warnings. Do not commit personal audio, model weights, local outputs or credentials.

Keep the canonical audio timebase unchanged. Do not fabricate character-level lyrics, downbeats, confidence probabilities or missing notes to fill an output. Backend failures must be visible and resumable. Update the schema version when making an incompatible project format change.

## Translation and releases

UI messages live in `src/music_studio/ui/static/i18n.js`. Add English translations
for the Chinese source messages and use named placeholders in dynamic `t()` calls.
Never translate song titles, lyrics or editor inputs. UI language must not change
song-language settings, request audio, reset playback or trigger inference.
Check both languages, dialogs, 720p and narrow layouts with real screenshots.

For a release, update the package version, changelog and `docs/releases/vX.Y.Z.md`,
validate a clean installation, then push `vX.Y.Z`. The release workflow checks the
tag/version, runs regression tests, builds ZIP/wheel/sdist/checksums and publishes
a preview. Do not claim remote CI succeeded based on local checks alone.
