param(
    [ValidateSet('cpu','cuda')][string]$Device = 'cpu',
    [string]$Python = '',
    [string]$ModelDir = '',
    [switch]$SkipDownload
)
$ErrorActionPreference = 'Stop'
$nextRepo = Split-Path $PSScriptRoot -Parent
$nextEnvironment = Join-Path $nextRepo '.venv-next-models'
$nextModelPython = Join-Path $nextEnvironment 'Scripts/python.exe'
if (-not $Python) { $Python = Join-Path $nextRepo '.venv-next/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $Python)) {
    throw 'Run scripts/setup-next.ps1 first, or pass -Python with Python 3.11 / 3.12.'
}
& $Python -X utf8 -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,13), 'Python 3.11 / 3.12 is required'"
if ($LASTEXITCODE -ne 0) { throw 'Choose Python 3.11 / 3.12.' }
if (-not (Test-Path -LiteralPath $nextModelPython)) {
    & $Python -m venv $nextEnvironment
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the separate Next model environment.' }
}
$nextTorchIndex = if ($Device -eq 'cuda') { 'https://download.pytorch.org/whl/cu121' } else { 'https://download.pytorch.org/whl/cpu' }
& $nextModelPython -m pip install 'torch==2.5.1' 'torchaudio==2.5.1' --index-url $nextTorchIndex
if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed. Check the network and device choice.' }
& $nextModelPython -m pip install -e ($nextRepo + '[inference]')
if ($LASTEXITCODE -ne 0) { throw 'Model dependency installation failed.' }
if (-not $ModelDir) { $ModelDir = Join-Path $nextRepo '.cache/models' }
if (-not $SkipDownload) {
    $env:PYTHONPATH = Join-Path $nextRepo 'src'
    & $nextModelPython -X utf8 -m music_studio models download --model-dir $ModelDir
    if ($LASTEXITCODE -ne 0) { throw 'Official model download failed. Completed cache files are retained.' }
}
Write-Host 'Next model environment is ready. Restart Start-Music-Studio-Next.cmd, then check Local models.'
Write-Host ('Model cache: ' + $ModelDir)
