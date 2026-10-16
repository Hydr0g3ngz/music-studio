# Factory creation assets / 创作素材

The application source is MIT. These assets have their own licenses.
软件源码为 MIT；本目录素材遵循各自许可。

## Instrument samples: VCSL

- Source: https://github.com/sgossner/VCSL
- Revision: `c1ea7bcc3c7309650ab0da9d15c9cd1fbc4a4c7e`
- Creator: Versilian Studios and VCSL contributors.
- License: CC0-1.0; full text in `LICENSE-VCSL.txt`.
- Changes: selection of 23 samples; leading silence trim, peak normalization,
  duration trim/end fade and stereo conversion; lossless PCM-16 FLAC encoding.
- This is a small single-layer sample pack, not the complete VCSL or an SFZ player.
- 本包为 23 个采样的轻量选集，经过起音裁剪、峰值调整、时长裁剪/淡出与格式转换；
  不是完整声库，不支持 SFZ 导入。其他未映射打击乐采用闭镲近似音色。

## Drum templates: Groove MIDI Dataset v1.0.0

- Source: https://magenta.withgoogle.com/datasets/groove
- Creators: Jon Gillick, Adam Roberts, Jesse Engel, Douglas Eck, David Bamman;
  Google LLC and the original drummers identified in the manifest.
- License: Creative Commons Attribution 4.0 International (CC BY 4.0).
- License text: https://creativecommons.org/licenses/by/4.0/legalcode
- Eight two-bar excerpts from the training split; beats 4–12 of source files.
  Human microtiming and velocity retained; fixed 0.12-beat note gates; source
  drum aliases 22→42 and 26→46. Original archive/file hashes and filenames
  are recorded in `manifest.json`.
- 模板保留原鼓手的微时序与力度；截取训练集中的两小节，统一短音符时值并映射鼓音高。
  请随发布作品保留来源与署名；界面可导出实际使用模板的署名文件。

Rebuild with `scripts/build_creation_library.py` from the repository root.
Rebuilding explicitly accesses the network; application playback/export are offline.
可从固定来源重建；重建需要联网，正常试听和导出不联网。
