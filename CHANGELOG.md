# Changelog / 更新记录

## 0.1.5 — Desktop icon and fullscreen / 图标与全屏

- A new waveform icon for the application, installer, desktop/Start shortcuts and browser.
- Native borderless fullscreen: use the top-right button or F11; Esc/F11 restores the previous window bounds and maximized state without reloading the page.
- Dark Windows caption in window mode; bilingual fullscreen labels follow the actual native/browser state.
- Small application updates reuse an existing complete GPU installation. First installs automatically fetch the verified v0.1.4 GPU base and apply the desktop/application update.
- 新图标与无边框全屏；安装器同时更新窗口程序与界面。已有 GPU 版保留环境、模型、歌曲与歌词修改。

## 0.1.4 — NVIDIA GPU installer / 显卡加速安装版

- Include PyTorch 2.5.1 + CUDA 12.1 and its CUDA/cuDNN libraries in the standalone installer.
- Automatic device selection uses a verified NVIDIA GPU. Probe actual CUDA computation and Whisper compute support in a disposable process, with a visible CPU fallback reason.
- GPU acceleration for Demucs separation, Whisper small lyrics and CREPE melody; librosa rhythm/harmony remain CPU processing.
- Upgrading the CPU installation preserves songs, corrections and models; remove obsolete CPU package metadata during upgrade.
- Native Windows installer downloads verified data parts with HTTP resume; offline parts work without commands. The matching application wheel is embedded and applied automatically.
- Keep GPU probes and analysis workers independent of the desktop control input pipe, fixing stalled Python subprocess startup on Windows.
- 安装后默认自动使用可用的 NVIDIA 显卡，无需配置 Python、CUDA Toolkit 或 cuDNN；界面显示 GPU 检查结果。

## 0.1.3 — Standalone song-analysis installer

- Windows desktop installer includes Python, CPU inference and basic Demucs, Whisper small and CREPE models. No terminal or separate basic-model download.
- Independent Music Studio application identity, installation, song storage and desktop window; composition and mixing belong to Music Workbench.
- Disable unbundled turbo and CUDA options in the CPU distribution. Source installations retain GPU and optional recognizers.
- High DPI, single-instance reopening and owned-server shutdown.
- 中英双语独立安装包，内置基础模型；歌曲分析与创作平台分开维护。

## 0.1.2 — 2026-10-15 · Preview / 预览版

Fix Qwen recognition failing after separation when starting with the Windows shortcut.
The launcher now connects the optional environment installed by `setup_lyrics.ps1`,
or accepts `-LyricsPython` for a custom environment. The workbench disables recognizers
whose Python dependencies are absent; the API rejects unavailable runtimes before
starting separation or creating a result revision. Older running backends prompt a restart.

修复双击启动后选择 Qwen、运行到歌词识别阶段才失败的问题。启动器会自动连接已安装的
歌词独立环境，也支持 `-LyricsPython` 自定义路径；界面停用缺少依赖的识别模式，
后台在开始分离音轨、创建结果版本前检查所需运行环境。旧后台会提示重启；原有结果保留。

## 0.1.1 — 2026-10-15 · Preview / 预览版

The first published preview. The 0.1.0 build was stopped during release validation.
Importing the compressed demo now also prepares canonical float WAV caches, so
later lyric recognition/alignment can reuse the normal worker contract. No neural
models or decoder packages are needed to prepare this cache. Added a
demo-to-inference regression check.

首个实际发布的预览版。0.1.0 构建在发布验收中停止；现将压缩示例在导入时准备为标准 float WAV
缓存，修复安装模型后对示例重新识别 / 对齐时找不到音轨的问题。此准备过程不依赖模型或 PyAV，
保留统一时间基准，并增加示例转入识别流程的回归检查。

## 0.1.0 — 2026-10-15 · Preview / 预览版

- Local workbench: vocals/backing, synchronized lyrics, vocal MIDI, chords and beats.
- 中文 / English interface switch; browser language detection and saved preference.
- Bundled, credited 45-second precomputed demo; no model download needed to explore.
- Windows launcher, preview/full installation modes, packaged wheel/source and checksums.
- Lyric text correction, review markers, contextual loops, version comparison and explicit candidate acceptance.
- Sing-along view with adjustable guide vocals; LRC/SRT/MIDI/audio/CSV/JSON export.
- Project search, rename, recoverable delete and Trash restore.
- Playback fixes: stable result polling, lazy stem caching and rapid seek/pause handling.
- 43-case component/lyric benchmark with provenance and separately reported timing coverage/error.

中文：首个公开预览版，提供完整本地分析工作台、中英切换、免模型授权示例、Windows 启动入口、
歌词纠错与版本核对、跟唱与导出、歌曲回收站，以及可复现 benchmark。修复反复载入音轨和快速拖动时暂停的问题。

This is an early release. The Windows ZIP requires Python 3.11/3.12 and an initial
dependency download. Models are optional downloads with their own licenses.
It is not a standalone EXE or a complete score/arrangement editor.

这是早期版本。Windows ZIP 需要 Python 3.11/3.12，首次安装依赖需联网；模型需另行下载并遵守各自许可。
本版本不是独立 EXE，也不是完整谱面或编曲编辑器。
