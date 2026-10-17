# Build the Windows installer

Music Studio builds independently. Use Windows x64, Python 3.12, the Windows .NET
Framework C# compiler, and at least 8GB of temporary disk space.

```powershell
python -m pip install -e ".[ui,dev]"
python -m pip wheel --no-deps --wheel-dir dist .
python scripts/prepare_installer_tools.py
$setup = Start-Process .artifacts/desktop-build-tools/innosetup-6.7.3.exe -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER',"/DIR=$PWD\.artifacts\desktop-build-tools\inno" -WindowStyle Hidden -Wait -PassThru
if ($setup.ExitCode -ne 0) { throw 'Compiler setup failed' }
python scripts/package_installer.py --wheel dist/music_studio_local-0.1.3-py3-none-any.whl --payload .artifacts/installer/payload --dist dist --tools .artifacts/desktop-build-tools
```

The builder downloads pinned CPython, CPU Torch, inference packages and three basic
model families; checks model hashes; emits DEPENDENCIES.json and BUNDLED-MODELS.json.
Use a fresh payload directory. --engine-env and --model-base can reuse a verified
private CPU environment and matching weights; external app bindings are removed.

Perform real offline analysis, playback, correction and export from the packaged
runtime before publishing. A local build does not establish fresh-Windows compatibility.
