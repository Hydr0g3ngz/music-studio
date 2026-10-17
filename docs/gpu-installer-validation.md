# Windows GPU installer validation / 显卡安装版验证

Music Studio v0.1.4 includes an independent embedded Python 3.12.10 runtime,
PyTorch/torchaudio 2.5.1+cu121, CUDA 12.1 and cuDNN 9.1. All basic model files
retain the v0.1.3 hashes: Demucs htdemucs, Whisper small and CREPE full.
This release changes distribution and device selection, not model accuracy.

## Local machine

Windows, RTX 4070 Laptop GPU (8,188 MiB), NVIDIA driver 591.74, 32GB RAM.
Other GPU families, a clean Windows VM, AMD/Intel acceleration and RTX 50-series
compatibility are not established by these results. This CUDA 12.1 runtime does
not include Blackwell support. A compatible NVIDIA graphics driver is required;
users do not need to install a CUDA Toolkit or cuDNN separately.

## Tests and offline inference

- 70 Python tests pass, including automatic CUDA selection, CPU fallback,
  rejecting an explicitly requested unavailable GPU before writing a job, and
  keeping unbundled turbo/dual-guide modes disabled in the GPU distribution.
- 19 JavaScript tests pass, including GPU readiness/failure messages, lyric
  editing, playback stability and bilingual UI switching without audio reloads.
- Ruff passes.
- Actual inference uses the packaged Python with `PYTHONHOME`/`PYTHONPATH` unset,
  and PATH restricted to that runtime and Windows system directories. No host
  Python, host CUDA Toolkit, external model directory or downloaded result is used.
- The credited bundled CC BY 3.0 demo's 10–22 second vocal passage is processed
  offline through all five analysis stages. It yields 2 lyric lines, 15 notes,
  3 chords, 25 beats and 9 validated assets with aligned audio lengths.

| Neural stage | Recorded device | Stage time | PyTorch allocation peak |
| --- | --- | ---: | ---: |
| Demucs separation | CUDA | 11.081 s | 549.3 MiB |
| Whisper small lyrics | CUDA | 29.278 s | Not measured by the PyTorch allocator |
| CREPE melody | CUDA | 17.628 s | 735.0 MiB |

The packaged analysis wall time is **102.812 seconds for 12 seconds of audio**,
including worker startup and library/model loading, excluding the initial
hardware probe and installer download. The installer was compressing concurrently.
This is an integration check, not a controlled performance comparison or a
prediction of full-song runtime. CTranslate2 GPU allocations are not included in
PyTorch peaks. Rhythm and harmony continue to use CPU/librosa.

After removing the build-only files, a second offline run processes the full
**45-second bundled excerpt in 64.437 seconds**, yielding 4 lyric lines, 52 notes,
15 chords, 89 beats and 9 validated assets. Library caches had already initialized;
this is not a cold-start comparison with the preceding test.

## Runtime packaging

Only PyTorch's link-time `.lib` files, C++ extension headers and CMake build files
are removed from the runtime payload. CUDA/cuDNN DLLs and model files are retained.
The package supports inference, not compiling custom PyTorch C++ extensions.

The base runtime installer is 2,200,626,889 bytes (SHA256
`ea38c1496a4231f7128fc58078062fb84fed87cd6ae9cef101832ae5b86ef165`).
It exceeds GitHub's single-asset limit, so the public EXE retrieves two data parts
with resumable HTTP downloads, checks each SHA256, then checks the assembled
installer. The matching application wheel is embedded in the native EXE and applied
after runtime installation. Matching parts next to the EXE allow installation
without network access.

Two installed desktop checks stalled at the 60-second and 180-second limits.
This was not slow CUDA initialization: a Python child inherited the controller's
input pipe while its main thread was reading that pipe. A minimal reproduction
stalls even for `print("child ready")`; with an independent null input, it finishes
in 0.046 seconds. GPU checks, analysis workers and external environment checks now
use independent null input. The GPU probe retains a 60-second limit. A regression
test exercises an external dependency check while the controller input is blocked.

After that fix, the installed controller's HTTP API detects the RTX 4070, resolves
**Automatic → CUDA**, and completes a fresh offline 12-second vocal analysis in
150.266 seconds including exports, lyric editing and delete/restore checks. Demucs,
Whisper and CREPE metrics all record CUDA. This first run from the installed path
includes model/library initialization; it is not a speed comparison with the
separate payload runs above. Both failed checks remain in the local logs.

Installation uses the user's previously selected program directory. That directory
had been absent before installation, so this validates a fresh GPU installation,
not an overlay onto existing CPU runtime files. The nine existing song-data files
retain their contents, sizes and timestamps.

The native installer was exercised against a local HTTP server with a pre-existing
8 MiB partial download. It sent HTTP Range, received 206, verified both data parts,
and assembled the exact base installer SHA256 above. Native offline installation
also completed and applied its embedded application wheel without external Python
or terminal commands.

“Automatic” uses an isolated actual CUDA calculation and Whisper compute-type
check. It selects CUDA when available; otherwise the UI explains why GPU is
unavailable and offers CPU. Explicit GPU requests fail before analysis starts
when that check fails. The desktop server keeps no model resident on the GPU.

中文：本轮验证关注安装包里的显卡推理是否真正运行，未宣称识别准确率提升。
分离、歌词和旋律的运行日志均记录 CUDA；节拍与和弦仍使用 CPU。
首次短片段耗时包含各阶段启动和模型加载，不应据此推算整首歌速度。
