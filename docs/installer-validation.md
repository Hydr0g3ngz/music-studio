# v0.1.3 installer validation

The Windows CPU distribution contains the original song-analysis product, with
Demucs htdemucs, CREPE full, Whisper small, and librosa rhythm/harmony processing.
There is no ACE-Step, arrangement engine or Music Workbench application code in
the payload. Its embedded Python has only distribution-local search paths.

Local validation on Windows, Intel Core Ultra 9 185H, 32GB RAM:

- 66 Python tests, including independent application identity and rejecting CUDA/turbo before starting work in the CPU distribution.
- 18 JavaScript tests, including playback stability, language switching, disabling unbundled modes, and preserving unsaved lyric text when closing the desktop window.
- Real HTTP workflow against the packaged embedded Python: import a 12-second credited demo crop, offline separation, transcription, melody, rhythm and harmony; download stems/MIDI/LRC/SRT; correct text; delete and restore while retaining the correction.
- CPU first-run wall time: **195.875 seconds for 12 seconds of audio**, including process startup and initial model/library loading. This is an integration measurement, not a model-quality benchmark or a prediction of full-song runtime.
- The cropped introduction yielded one lyric line and two notes. Those counts describe this input, not transcription accuracy.

The installer is unsigned. Bundled model files have pinned SHA-256 hashes, Python
and third-party licenses are retained, and the WebView2 runtime prerequisite is
checked for a valid Microsoft signature before compilation.
The installer also carries Microsoft VC++ 14.44 x64 and installs it when the
corresponding system runtime is missing or older. Its hash and signature are checked.

This is local validation on a development Windows machine. A fresh Windows VM,
different CPU families, and first-time WebView2 installation remain separate
compatibility checks; they have not been established by this report.
