# Changelog / 更新记录

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
