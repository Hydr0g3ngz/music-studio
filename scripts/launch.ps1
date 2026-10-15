param(
    [ValidateRange(1024, 65500)][int]$Port = 8765,
    [string]$Python = 'py',
    [switch]$Online
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $projectPython)) {
        Write-Host 'First start: installing the preview runtime (no neural models). Internet is required.'
        & (Join-Path $PSScriptRoot 'setup.ps1') -Mode preview -Python $Python
    }
    & $projectPython -c 'import music_studio, fastapi, uvicorn, multipart'
    if ($LASTEXITCODE -ne 0) { throw 'Runtime is incomplete. Run scripts/setup.ps1 -Mode preview and retry.' }
    # Find a free local port without terminating any existing application.
    $selectedPort = $Port
    while ($selectedPort -lt ($Port + 32)) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $selectedPort)
        try { $listener.Start(); break } catch { $selectedPort++ } finally { $listener.Stop() }
    }
    if ($selectedPort -ge ($Port + 32)) { throw 'No free local port found. Try -Port 9000.' }
    $uiArguments = @('-m', 'music_studio', 'ui', '--workspace', 'outputs/ui', '--model-dir', '.cache/models', '--port', "$selectedPort", '--open')
    if (-not $Online) { $uiArguments += '--offline' }
    Write-Host "Music Studio: http://127.0.0.1:$selectedPort"
    Write-Host 'Choose Try the demo for immediate playback. Keep this window open; Ctrl+C stops the server.'
    Write-Host 'Analyze your own songs: scripts/setup.ps1 -Mode full -Device cuda -DownloadModels'
    & $projectPython @uiArguments
    if ($LASTEXITCODE -ne 0) { throw "Music Studio exited with code $LASTEXITCODE. See the log above." }
} finally { Pop-Location }
