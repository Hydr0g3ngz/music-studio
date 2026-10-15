# v0.1.1 发布验证 / Release validation

本地验证日期 / Local validation: **2026-10-15**, Windows, Python 3.12.4.

## 实际完成 / Completed checks

- Python: **60 passed**; covers source decoding, schema, exports, pipeline caching,
  result revisions, conflicts, review markers, upload/trash and the bundled demo.
- Node: **15 passed**; actual status-poll/player logic, lazy stems, cancelled loads,
  pause/rapid seeks, saved language preference and language redraw preserving
  playback, version, lyrics and unsaved editor input.
- Ruff, JavaScript syntax and PowerShell parser checks passed.
- A separate non-editable virtual environment installed the wheel with `[ui]`
  plus `httpx` for validation. `torch`, `demucs`, `faster_whisper`, `qwen_asr`,
  `av`, `librosa` and `scipy` were absent. The installed wheel loaded the actual UI,
  imported the bundled demo, served all tracks/exports, saved lyric corrections,
  updated LRC, deleted/restored the project and returned an actionable missing-inference error.
- The demo copy was checked against its packaged SHA-256 manifest. Its recording,
  separated/compressed derivatives and estimated annotations retain CC BY 3.0 attribution.
- A real cached-model smoke check reran the new demo's lyrics with Whisper small
  on CUDA in 17.359s. It completed in a new result version and preserved all three
  decoded audio hashes. This checks the demo-to-worker path, not lyric accuracy
  or cold end-to-end performance.
- The Windows ZIP was extracted into a folder containing spaces. Its actual
  PowerShell 5.1 setup entry installed the wheel in preview mode, and the launcher
  found port 8772 while 8765–8771 were occupied, without stopping those services.
- Real browser checks covered Chinese/English shell, status, editor, track selection,
  language persistence on reload and switching language during playback. The clock
  continued at the same song position; language redraw did not request audio.
- 1280×720 desktop controls and a 430px-wide layout were inspected in both languages;
  no horizontal page overflow was observed. The transport stays in document flow.

中文：在独立、非 editable 的无模型环境验证实际 wheel，而不是复用开发环境的代码。
示例可离线使用，改字后导出同步更新，删除后能恢复；语言切换不更改歌词或重置播放器。

## 复现 / Reproduce

```powershell
py -3.12 -m venv .artifacts/release-check
$wheel = (Resolve-Path dist/music_studio_local-0.1.1-py3-none-any.whl).Path
& .artifacts/release-check/Scripts/python.exe -m pip install "$wheel[ui]" httpx
& .artifacts/release-check/Scripts/python.exe scripts/verify_release.py --no-models
```

Run the verifier from outside an editable development checkout when inspecting
an independently downloaded wheel. It asserts that the import comes from site-packages.

## 范围 / Limits of this validation

This is a clean-venv check on the existing Windows machine, **not** a fresh OS or
a second physical machine. Real CPU/CUDA inference was validated in earlier local
pipeline runs; it was not re-benchmarked as part of translation and packaging.
The ZIP requires Python and first-time dependency installation. No standalone EXE
or bundled Python runtime is claimed. Remote CI/Release status is authoritative
only after the corresponding GitHub Actions run completes.

这是当前 Windows 机器上的干净虚拟环境验证，不等于全新系统或第二台电脑验收。
本轮未因翻译或打包重新声称模型准确率提升；真实推理结果见既有 benchmark 与 smoke test。
远程检查与发布是否成功，以 Actions / Releases 实际结果为准。
