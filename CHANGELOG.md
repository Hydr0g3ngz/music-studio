# Changelog / 更新记录

## 0.2.0.dev2 — Speech cleanup / 语音清理开发预览

CPU speech cleanup with fixed, explicitly installed GTCRN / DPDFNet2 weights; integrated
LUFS, true-peak and LRA measurement; static-gain normalization with peak constraints;
synchronized matched A/B without reloading tracks. Sixteen UI/MCP/Codex tools share the
same immutable assets and reversible previews. Includes a credited CC BY 4.0 speech demo,
32 paired regression cases with per-case failures, and bilingual setup/results.
Older Next APIs hide unsupported controls; the launcher detects mismatched running versions.
Classic v0.1.2 and prior workspaces remain separate.

新增 CPU 语音清理（权重明确安装）、LUFS / 真峰值 / LRA、受峰值约束的音量统一、
同位置等响度 A/B。16 个界面/MCP/Codex 工具共用素材与可撤销预览，附 CC BY 4.0
语音示例、32 对回归及逐例退步、中英说明。新页面兼容旧 Next 能力清单，启动器检测旧后台。
经典版与已有工作区独立保留。GTCRN 为实验项；DPDFNet 也有 STOI 退步，见实测报告。

## 0.2.0.dev1 — Next development / 开发预览

The 0.2.0.dev0 release gate stopped on an asynchronous test's three-second deadline
on a shared Windows runner. The test now allows time for fixture exports to finish;
the success assertions and release checks are retained. No 0.2.0.dev0 release was published.

0.2.0.dev0 发布被 Windows 共享运行器上过短的异步测试等待时间拦住；
现给测试导出留足完成时间，保留所有成功断言与发布检查。未发布 0.2.0.dev0 安装包。

An independent audio-editing preview with waveform selections, typed PCM operations,
immutable audition candidates, undo/redo and WAV export. MCP and an experimental Codex
app-server bridge share the same project state and events. A separate launcher/runtime/output
retains v0.1.2. Seven local capability entries share a persistent serial queue, runtime checks,
immutable assets and text-correction versions through 15 UI/MCP/Codex tools. Real model runs
validate the path. Rest-preserving melody decoding improves vocadito but regresses on GTSinger;
it is an experimental option and does not replace the classic default.

独立的音频编辑预览：波形选区、非破坏处理、候选试听、撤销/重做和 WAV 导出；
MCP 与实验性 Codex 连接共用项目状态。启动器、环境和输出独立，稳定版 v0.1.2 保留。
新增本地模型清单、隔离环境检查、持久化队列、固定素材与转写改字版本，15 个共享工具覆盖
7 个能力入口，均完成真实模型验证。保留休止的音符解码作为实验选项，因跨数据集退步而未替换默认值。

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
