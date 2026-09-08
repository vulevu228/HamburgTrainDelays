<#
    Run the one-shot collector, then commit & push hamburg_delays.csv if it changed.
    Designed to be fired every ~15 min by Windows Task Scheduler
    (see install_task.ps1). All output is appended to collector.log.
#>
param(
    [string]$Python = "python"
)

# git writes progress to stderr; don't let that abort the script
$ErrorActionPreference = "Continue"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$log = Join-Path $repo "collector.log"
function Log($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), ($msg -join " ")
    Add-Content -Path $log -Value $line -Encoding utf8
}
function Git { (& git @args 2>&1) -join " " }

$out = & $Python (Join-Path $PSScriptRoot "hamburg_collector.py") 2>&1
if ($LASTEXITCODE -ne 0) {
    Log "collector FAILED: $out"
    exit 1
}
Log $out

Git add hamburg_delays.csv | Out-Null
& git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Log "no dataset change - nothing to commit"
    exit 0
}

$stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm 'UTC'")
Git commit -m "data: hamburg delays $stamp" | Out-Null

$push = Git push
if ($LASTEXITCODE -ne 0) {
    Log "push FAILED ($push) - commit saved locally, will go out next run"
    exit 1
}
Log "committed + pushed: $stamp"
