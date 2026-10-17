# Third-party components and model sources

The optional [Beat This!](https://github.com/CPJKU/beat_this) implementation and authors' checkpoints use MIT terms. small0 is pinned by SHA-256; relevant fold checkpoints use the authors' official-cloud `OC-Checksum` SHA-1 metadata (2026-10-15). Models stay outside Git. small0/final0 training includes GuitarSet, so their diagnostic results do not establish held-out accuracy.

Music Studio's original code is MIT licensed. Dependencies and model weights retain their own licenses. Weights are not committed to Git or relicensed. The v0.1.3 installer includes basic htdemucs, CREPE full and Whisper small weights with upstream terms and a SHA-256 manifest. Optional models download separately. This list does not replace the upstream license files retained in distribution packages.

| Component | Use | Upstream license/source |
| --- | --- | --- |
| Demucs 4.0.1 | Vocal/instrumental separation | [MIT, Meta / Alexandre Défossez](https://github.com/facebookresearch/demucs/blob/main/LICENSE) |
| htdemucs / htdemucs_ft | Separation weights | [Official Demucs model documentation](https://github.com/facebookresearch/demucs), downloaded from `dl.fbaipublicfiles.com/demucs/` with upstream hash checks |
| faster-whisper 1.2.1 | Local ASR and word timestamps | [MIT, SYSTRAN](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE) |
| CTranslate2 4.6.0 | ASR inference runtime | [MIT, OpenNMT](https://github.com/OpenNMT/CTranslate2/blob/master/LICENSE) |
| Converted Whisper checkpoints | ASR weights | [SYSTRAN model collection](https://huggingface.co/Systran); consult the selected checkpoint's model card, e.g. [small](https://huggingface.co/Systran/faster-whisper-small) |
| Qwen3-ASR / Qwen3-ForcedAligner | Optional lyric recognition and forced alignment | [Apache-2.0, official Qwen repository](https://github.com/QwenLM/Qwen3-ASR); weights and commits in `src/music_studio/lyric_models.py` |
| HeartTranscriptor-oss | Optional singing-tuned Whisper recognition | [Apache-2.0, HeartMuLa](https://huggingface.co/HeartMuLa/HeartTranscriptor-oss); [official inference](https://github.com/HeartMuLa/heartlib/tree/main/examples) |
| torchcrepe 0.0.24 | Vocal pitch | [MIT, Max Morrison](https://github.com/maxrmorrison/torchcrepe/blob/master/LICENSE); the package contains converted [CREPE](https://github.com/marl/crepe) weights |
| PyTorch / torchaudio | Tensor/audio runtime | [PyTorch license](https://github.com/pytorch/pytorch/blob/main/LICENSE), [torchaudio license](https://github.com/pytorch/audio/blob/main/LICENSE) |
| librosa | Resampling, pYIN, chroma and beat baseline | [ISC](https://github.com/librosa/librosa/blob/main/LICENSE.md) |
| PyAV / FFmpeg | Audio decoding | [PyAV license](https://github.com/PyAV-Org/PyAV/blob/main/LICENSE.txt); FFmpeg and binary build terms remain applicable to the upstream distribution |
| python-soundfile / libsndfile | Float WAV export | [SoundFile licensing](https://github.com/bastibe/python-soundfile#license) |
| mido | MIDI export | [MIT](https://github.com/mido/mido/blob/main/LICENSE) |

The Demucs upstream repository is archived. Its version is intentionally pinned for the initial backend. Replacement backends are isolated behind the same project schema.

The Windows runtime also pins CTranslate2 4.6.0 and setuptools <81. This combination was selected during local inference verification; CTranslate2 4.6.0 still imports `pkg_resources`.

The optional benchmark tools use [mir_eval](https://github.com/mir-evaluation/mir_eval) (MIT) and [remotezip](https://github.com/gtsystem/python-remotezip) (MIT). The fixed audio/reference subset reuses Jam-ALT, JamendoLyrics, GTSinger, GuitarSet and MUSDB preview material under their original dataset/per-track terms. Source credits, dataset versions, per-file hashes and use limits are recorded in [benchmarks/README.md](benchmarks/README.md) and [suite-v1.json](benchmarks/suite-v1.json). These datasets and derived audio are optional local evaluation assets and are not included in this repository's MIT grant.

The v4 extension uses 17 manually aligned MIR-1K recordings and character boundaries from the [ASRU 2023 author repository](https://github.com/navi0105/LyricAlignment), pinned at `1c39cd0369ce7dc55fa45277b59215b333d3a817`. Audio is retrieved from a version-pinned public mirror when the original host is unavailable. The mirror's license metadata is not treated as a replacement for the original source terms; the annotation repository has no explicit license grant. Only source metadata, hashes, code and numerical measurements are included here. Audio, mixed derivatives, annotation text and recognition transcripts remain ignored local assets. See [the v4 manifest](benchmarks/suite-v2-mir1k.json).

Development smoke tests may download `facebookresearch/demucs/test.mp3` into the ignored `.artifacts` directory. That audio is used only for local interoperability checks and is not redistributed as a Music Studio sample or claimed to be owned by this project. The synthetic tone/chord/click tests are generated by the test code itself.

The singing smoke test uses a 30-second excerpt (20–50 s) of **Let's Go Fishin' — Karissa Hobbs**, obtained via librosa's `fishin` example. The source is [Creative Commons Attribution 3.0](https://creativecommons.org/licenses/by/3.0/), according to [librosa's attribution file](https://librosa.org/data/audio/Karissa_Hobbs_-_Lets_Go_Fishin.txt), with the [original Free Music Archive page](https://freemusicarchive.org/music/Karissa_Hobbs/Age_of_Flowers/09_Lets_Go_Fishin). Local tests crop, separate and analyze the recording; generated transcriptions and notes are machine estimates, not author-supplied notation. Full recordings and private test outputs remain ignored.

The workbench now bundles a **45-second precomputed preview** in
`src/music_studio/ui/demo/`: a crop from the start, original/vocal/backing Ogg
previews, machine-estimated lyrics/timing/notes/chords/beats and exports. Changes
are identified in its [attribution](src/music_studio/ui/demo/ATTRIBUTION.md) and
hash manifest. These audio derivatives retain **CC BY 3.0**, are not relicensed
under MIT and are not benchmark references. The UI retains artist/license/source
metadata in every imported demo copy. No endorsement by the artist is implied.

中文：代码采用 MIT，依赖和模型遵守各自许可。随包提供的 45 秒示例是 Karissa Hobbs
的 CC BY 3.0 授权录音的截取、分离与压缩衍生物，包含机器估计结果，不属于 MIT 音频资产，
也不是人工标注。完整署名、改动说明和文件哈希随示例保留；其他测试音频和标注正文不随仓库发布。基础模型随 Windows 安装器分发，保留上游许可。

## Windows desktop distribution

- CPython 3.12.10: PSF license; runtime includes LICENSE.txt.
- PyTorch / torchaudio 2.5.1+cpu: upstream BSD-style licenses retained in package metadata.
- WebView2 SDK 1.0.4258.31: Microsoft terms in WEBVIEW2-SDK-LICENSE.txt; signed Evergreen runtime installer included as a prerequisite.
- Inno Setup 6.7.3: build compiler; https://jrsoftware.org/isinfo.php.
- Package .dist-info licenses are retained; DEPENDENCIES.json lists shipped versions.
- Whisper small weights: MIT; https://huggingface.co/Systran/faster-whisper-small and https://github.com/openai/whisper/blob/main/LICENSE.
- CREPE full weights: MIT; https://github.com/maxrmorrison/torchcrepe/blob/master/LICENSE and https://github.com/marl/crepe/blob/master/LICENSE.
- Demucs htdemucs weights: MIT; https://github.com/facebookresearch/demucs/blob/main/LICENSE.
