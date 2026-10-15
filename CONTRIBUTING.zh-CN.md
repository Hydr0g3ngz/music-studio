# 贡献指南

[English](CONTRIBUTING.md) · [路线图](docs/roadmap.md)

欢迎使用中文或英文反馈和贡献。先说明具体使用场景及修改后行为；较大的模型或交互改动建议先开 issue，
小修复可以直接提交 PR。请使用授权示例或可分享的合成音频复现，避免公开个人歌曲与隐私信息。

## 本地开发

Python 3.11 / 3.12；前端为 HTML/CSS/JS，无构建步骤和外部 CDN。
不做神经推理时不需要安装 PyTorch 或模型：

```sh
python -m pip install -e ".[ui,benchmark,dev]"
python -m ruff check .
python -m pytest -q
node --test tests/ui_playback.test.cjs tests/ui_i18n.test.cjs
python scripts/package_release.py
```

Node 测试使用内置 runner，推荐 Node 22，无 npm 依赖。
Windows 默认测试临时目录权限有问题时可指定新的 `--basetemp=.artifacts/pytest-your-run`。
安装、预计算示例、API、版本、回收站与播放回归不下载模型；它们验证工程行为，不能证明识别准确率。

## 界面与翻译

界面位于 `src/music_studio/ui/static/`，双语消息在 `i18n.js`。
保留中文源消息并添加英文映射，动态文案使用 `t()` 与命名参数。歌词、歌曲名、用户输入与模型预测不能进入翻译器。
界面语言与“歌词语言”是独立选项，切换界面语言不能重建播放器、重置项目或触发推理。

修改界面后检查中英文、窄屏、720p、键盘访问、弹窗、无结果、错误、导出与回收站；
PR 提供真实截图。保持三轨同一个 Web Audio 时钟，实际浏览器验证连续试听和快速拖动。

## 模型与 benchmark

修改推理适配器需另行执行真实模型 smoke test、`music-studio validate OUTPUT`，并报告硬件、依赖、
模型修订版、资源范围和警告。评测命令、数据来源与冻结规则见 [benchmark 说明](benchmarks/README.md)。

禁止改动已冻结的 manifest 原始字节和确认集划分；不在确认集上调参。分开报告语言、录音域、
文字错误、匹配覆盖、条件时间误差及失败；同时说明未改善之处与训练重叠未知的限制。
源音频、标注正文、模型输出和权重保留本地，只有已明确授权的内置体验示例可进入仓库。

不能用均匀切字捏造词时间，不能把模型分数或核对标记当成正确率。保持统一原始音频时间基准，
失败需可见、可恢复。项目格式有不兼容变更时升级 schema。

## 发布

修改包版本、更新 `CHANGELOG.md` 和 `docs/releases/vX.Y.Z.md`，完成检查与干净环境验证，
再推送对应 `vX.Y.Z` 标签。发布工作流校验版本、运行测试、构建 ZIP / wheel / 源码与 SHA-256，
并发布为 preview。不要把仅本地通过的测试描述成远程 CI 已通过。
