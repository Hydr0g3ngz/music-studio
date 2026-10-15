param(
    [string]$Python = '.venv/Scripts/python.exe',
    [ValidateSet('qwen','aligner','heart')][string[]]$Models = @('qwen'),
    [switch]$SkipDownload
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot
$runtimeRoot = Join-Path $projectRoot '.artifacts/lyrics-env'
if (-not (Test-Path -LiteralPath (Join-Path $runtimeRoot 'Scripts/python.exe'))) {
    & $Python -m venv $runtimeRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not create lyric runtime' }
}
$basePackages = & $Python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])'
$importPath = @($basePackages, (Join-Path $projectRoot 'src')) -join "`n"
[System.IO.File]::WriteAllText((Join-Path $runtimeRoot 'Lib/site-packages/music_studio_base.pth'), $importPath + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
$lyricPython = Join-Path $runtimeRoot 'Scripts/python.exe'
& $lyricPython -m pip install --disable-pip-version-check 'qwen-asr==0.0.6' 'gradio==5.49.1' 'qwen-omni-utils==0.0.9' 'huggingface-hub==0.36.2' 'tokenizers==0.22.2'
if ($LASTEXITCODE -ne 0) { throw 'Could not install optional lyric dependencies' }
& $lyricPython -c 'from qwen_asr import Qwen3ASRModel, Qwen3ForcedAligner; print("Lyric runtime ready")'
if ($LASTEXITCODE -ne 0) { throw 'Optional runtime import check failed' }
if (-not $SkipDownload) {
    & $Python scripts/download_lyric_models.py --model $Models
    if ($LASTEXITCODE -ne 0) { throw 'Model download or checksum verification failed' }
}
Write-Host 'Start with --lyrics-python .artifacts/lyrics-env/Scripts/python.exe'
