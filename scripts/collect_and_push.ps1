<#
    Run the one-shot collector, then commit & push hamburg_delays.csv if it changed.
    Designed to be fired every ~15 min by Windows Task Scheduler
    (see install_task.ps1). All output is appended to collector.log.
#>
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$log = Join-Path $repo "collector.log"
function Log($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $log -Value $line -Encoding utf8
}

try {
    $out = & $Python (Join-Path $PSScriptRoot "hamburg_collector.py") 2>&1
    Log ($out -join " | ")
}
catch {
    Log "collector FAILED: $_"
    exit 1
}

# stage only the tracked dataset
& git add hamburg_delays.csv | Out-Null

& git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Log "no dataset change - nothing to commit"
    exit 0
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm 'UTC'")
& git commit -m "data: hamburg delays $stamp" | Out-Null

& git push 2>&1 | ForEach-Object { Log "push: $_" }
if ($LASTEXITCODE -ne 0) {
    Log "push FAILED (commit is saved locally, will go out next run)"
    exit 1
}
Log "committed + pushed"
