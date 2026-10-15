param(
    [string]$Python = '',
    [string]$ModelDir = '',
    [string]$Workspace = 'outputs/next',
    [ValidateSet('gtcrn','dpdfnet2-48k')][string]$Model = 'dpdfnet2-48k',
    [switch]$SkipDownload
)
$ErrorActionPreference = 'Stop'
$nextRepo = Split-Path $PSScriptRoot -Parent
if (-not $Python) {
    foreach ($cleanupRuntime in @('.venv-next/Scripts/python.exe', '.artifacts/workbench-env/Scripts/python.exe')) {
        $cleanupCandidate = Join-Path $nextRepo $cleanupRuntime
        if (Test-Path -LiteralPath $cleanupCandidate) { $Python = $cleanupCandidate; break }
    }
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    throw 'Run scripts/setup-next.ps1 first, or pass -Python with the Next interpreter.'
}
& $Python -X utf8 -c "import sys; assert (3,11) <= sys.version_info[:2] < (3,13), 'Python 3.11 / 3.12 is required'"
if ($LASTEXITCODE -ne 0) { throw 'Choose Python 3.11 / 3.12.' }
& $Python -m pip install -e ($nextRepo + '[cleanup]')
if ($LASTEXITCODE -ne 0) { throw 'Optional speech cleanup installation failed.' }
if (-not [IO.Path]::IsPathRooted($Workspace)) { $Workspace = Join-Path $nextRepo $Workspace }
$cleanupRuntimeFile = Join-Path $Workspace '.studio-runtime.json'
if (-not $ModelDir -and (Test-Path -LiteralPath $cleanupRuntimeFile)) {
    $cleanupSavedRuntime = Get-Content -LiteralPath $cleanupRuntimeFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cleanupSavedRuntime.model_dir) { $ModelDir = $cleanupSavedRuntime.model_dir }
}
if (-not $ModelDir) { $ModelDir = Join-Path $nextRepo '.cache/models' }
if (-not $SkipDownload) {
    $env:PYTHONPATH = Join-Path $nextRepo 'src'
    & $Python -X utf8 -m music_studio.studio.cleanup download --model-dir $ModelDir --model $Model
    if ($LASTEXITCODE -ne 0) { throw 'Official speech model download or checksum verification failed.' }
}
Write-Host 'CPU speech cleanup is ready. Restart Next, then check Local models.'
Write-Host ('Model cache: ' + $ModelDir)
