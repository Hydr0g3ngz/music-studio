# 旋律与 MIDI：候选模型实测

[English](melody-next.en.md) · 2026-10-16 · [逐例 JSON](../benchmarks/results/melody-next-2026-10-16.json)

**结论：暂不替换默认模型。** ROSVOT 在既有 GTSinger 回归上明显更好，
但在独立的 vocadito 数据上退步；Basic Pitch 在 GTSinger 上也未超过现有算法。
这次实验不把换模型、改善合成音色或修复时间序列化混为同一种进步。

## 评测协议

- 原有 GTSinger 12 段（中文/英文各 6 段）继续冻结，用作工程回归，已经参与过开发。
- 新增 [vocadito](https://zenodo.org/records/5578807) 全部 40 段、28 位歌手、7 种语言。
  [清单](../benchmarks/vocadito-v1.json) 固定音频、f0、两套音符标注的 SHA256。
- vocadito 是单人清唱，不能据此承诺复杂混音中的效果；两位人工音符标注者 A1 / A2 分别计分。
- 起音容差 50 ms、音高容差 50 cents；止音容差为 `max(50 ms, 20% 音符时长)`。
  使用 `mir_eval 0.8.2`，按片段取宏平均。失败案例进入分母并计零，不挑选成功样本。
- 模型仅接收音频，不接收参考歌词、音符时间或真值词边界。ROSVOT 使用 RWBD 预测词边界，
  阈值使用官方推理默认值 0.85 / 0.5，未在 vocadito 上调阈值。
- 输出 MIDI 后再读取，核对音高、音符数量、同音重叠与绝对秒数，最大时间误差阈值 10 ms。
- 逐帧 f0 单独计分；稳定引擎的无声 `null` 先转为 0 Hz。两套最终结果已用修正后的同一评分函数
  重新核算，全部 80 个片段的数值与保留结果一致。

## 音符结果

以下均为 F1 百分数，不能当成“正确音符的百分比”。

| 数据 / 指标 | CREPE + stable | Basic Pitch | ROSVOT + RWBD |
| --- | ---: | ---: | ---: |
| GTS 中文：起音+音高 | 30.6 | 19.8 | **59.8** |
| GTS 英文：起音+音高 | 38.8 | 19.5 | **48.9** |
| GTS 中文：包含止音 | 16.6 | 10.8 | **56.3** |
| GTS 英文：包含止音 | 20.8 | 6.3 | **36.9** |
| vocadito A1：起音+音高 | **45.6** | 未测 | 26.0 |
| vocadito A2：起音+音高 | **42.0** | 未测 | 27.0 |
| vocadito A1：包含止音 | **25.7** | 未测 | 18.5 |
| vocadito A2：包含止音 | **22.9** | 未测 | 21.6 |

ROSVOT 在 vocadito 的起音+音高分数相对 CREPE，A1 有 39/40 段退步，A2 有 37/40 段退步。
按歌手聚类、2000 次重采样的配对差值 95% 区间分别为 −23.3 至 −15.9、−18.9 至 −11.1
个百分点；这是当前样本的工程估计，不是跨所有歌唱场景的保证。

| vocadito 逐帧指标（宏平均） | CREPE | ROSVOT 所用 RMVPE |
| --- | ---: | ---: |
| Raw Pitch Accuracy | 98.07% | 98.20% |
| Raw Chroma Accuracy | 98.15% | 98.28% |
| Voicing Recall | 99.09% | 99.83% |
| Voicing False Alarm | 27.37% | 31.27% |

高逐帧音高准确率与低音符 F1 同时出现，提示应重点检查起止音、重复同音、无声/辅音间隙，
不能据此证明每个片段的音高都没有问题。下一步优先比较起音感知分段和保留休止的解码，
再用冻结清单检查退步，避免直接把新的模型当成更好的默认值。

## 资源与 MIDI 排查

本机为 RTX 4070 Laptop 8GB，PyTorch 2.5.1+cu121，4 个 Torch CPU 线程。
vocadito 片段的单段推理中位数：CREPE 1.04 s，ROSVOT 0.51 s；
最大 `torch.cuda.max_memory_allocated` 分别约 734 MiB 与 708 MiB。
这不包含驱动、CUDA 上下文、其他 GPU 程序或进程内存，不能外推整首长歌和其他 AI 模型。

所有最终实验均完成，MIDI 往返检查通过。还只读检查了 3 首已有歌曲的原 MIDI，
最大时间差 0.354 ms，音高与已保存的音符一致；这只排除了明显的序列化时间漂移，
不代表音符与原唱一致。用户觉得“旋律不对”的问题仍需要实质性改进转录和分段。

Basic Pitch 的 ONNX Runtime 1.31.0 在本机导入时出现原生崩溃，实验使用独立的 1.20.1
兼容目录完成；没有修改稳定版运行环境。因此模型健康检查应在隔离进程里实际导入，
不能仅凭包已安装就显示“可用”。

## 复现与来源

入口为 [GTS 评测脚本](../scripts/evaluate_melody_next.py)、
[vocadito 评测脚本](../scripts/evaluate_vocadito.py)、
[实验适配器](../scripts/rosvot_adapter.py)。每次使用新的输出目录，保留运行代码快照、
模型与数据哈希、原始输出和逐例分数。公开 JSON 保留实际运行身份与最终评分核验记录；
本地运行快照不等于当前脚本逐字节相同，后续增加了 CPU 选项与输入校验。

先安装仓库的 `[benchmark]` 依赖及实验环境中的 Torch、torchaudio、torchcrepe、pyworld、pretty_midi、PyYAML；
ROSVOT 权重按作者 README 获取。已验证的具体版本保存在逐例 JSON，模型推理不随常规测试自动运行。
数据可用校验过的下载器准备：

```bash
python scripts/download_vocadito.py --data /data/vocadito
python scripts/evaluate_vocadito.py --data /data/vocadito --backend crepe --output runs/vocadito-crepe
python scripts/evaluate_vocadito.py --data /data/vocadito --backend rosvot --upstream /path/ROSVOT --checkpoints /path/checkpoints --output runs/vocadito-rosvot
```

默认实验设备为 CUDA，可用 `--device cpu`。推理实验依赖单独安装，不属于无需模型的编辑安装。
ROSVOT 适配器当前只支持小于 30000 个模型帧的片段，明确拒绝超长输入；尚未接入生产长曲。

- [ROSVOT](https://github.com/RickyL-2000/ROSVOT)：`3c8332bf43adae35f6e4d64971862f2f6139b310`，
  Ruiqi Li，MIT 代码；[许可副本](licenses/ROSVOT-MIT.txt)。权重从作者的官方链接下载，未在本仓库再分发。
- [Basic Pitch](https://github.com/spotify/basic-pitch)：`fa5997af0a8210982619003269994a1be25eddf3`，
  Spotify，Apache-2.0，官方 ONNX 模型与默认推理。
- vocadito：Rachel Bittner、Katherine Pasalo、Juan José Bosch、Gabriel Meseguer Brocal、David Rubinstein，
  2021，CC BY 4.0，[数据记录](https://zenodo.org/records/5578807)。本仓库只包含清单和指标，不分发录音。

现有 GTSinger 数据的许可、来源与选择规则继续沿用 [原基准说明](../benchmarks/README.md)。
