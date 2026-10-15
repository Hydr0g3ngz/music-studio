# Speech cleanup demo

Source: Cassia Valentini-Botinhao (2017), *Noisy speech database for training speech
enhancement algorithms and TTS models, 2016*, University of Edinburgh / CSTR.
[Dataset and attribution](https://doi.org/10.7488/ds/2117).
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
[Publisher's licence](https://datashare.ed.ac.uk/server/api/core/bitstreams/7e7bc32f-e94a-436a-8e97-416a972c7e1a/content).

The original noisy test utterances p232_025, p232_398, p232_362, p232_226,
p257_037, p257_219, p257_312 and p257_018 are concatenated with 10 ms edge fades
and 350 ms silent gaps, then encoded as 16-bit FLAC. Their original WAV hashes
and the resulting FLAC hash are recorded in `manifest.json`.
Import decodes this edited example to the normal 44.1 kHz stereo float timeline.
No enhanced output is bundled: the user's explicit cleanup task runs the model locally.

This is an illustrative demo assembled after pilot evaluation, using the first four
frozen pilot items per test speaker. It is not a blind test or a full dataset result.
The authors, speakers and University do not endorse Music Studio.

来源为爱丁堡大学 / CSTR 的 VoiceBank-DEMAND 含噪测试语音，作者 Cassia Valentini-Botinhao，
2017，CC BY 4.0。上述八条录音加入 10 ms 首尾淡化与 350 ms 间隔后拼接为示例；
模型处理结果不随包提供，点击处理时才在本机运行。完整来源、修改和校验值见上方及清单。
