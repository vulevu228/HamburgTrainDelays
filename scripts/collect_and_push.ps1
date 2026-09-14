<#
    Run the one-shot collector, then commit & push hamburg_delays.csv if it changed.
    Designed to be fired every ~15 min by Windows Task Scheduler
    (see install_task.ps1). All output is appended to collector.log.

    Mirrors .github/workflows/hamburg_delays.yml: reset to origin/main
    BEFORE collecting, then retry the whole collect+commit+push cycle on a
    rejected push. hamburg_collector.py's upsert() rewrites the entire CSV
    (one row per train_id, whole file re-sorted) each run, so rebasing or
    merging that commit's diff onto a different origin tip collides on
    almost every line - always re-collect from the latest base instead.
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
function RunGit { (& git.exe @args 2>&1) -join " " }

$pushed = $false
for ($attempt = 1; $attempt -le 5; $attempt++) {
    RunGit fetch --quiet origin main | Out-Null
    RunGit reset --hard --quiet origin/main | Out-Null

    $out = & $Python (Join-Path $PSScriptRoot "hamburg_collector.py") 2>&1
    if ($LASTEXITCODE -ne 0) {
        Log "collector FAILED: $out"
        exit 1
    }
    Log $out

    & git.exe diff --quiet -- hamburg_delays.csv
    if ($LASTEXITCODE -eq 0) {
        Log "no dataset change - nothing to commit"
        exit 0
    }

    RunGit add hamburg_delays.csv | Out-Null
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd HH:mm 'UTC'")
    RunGit commit --quiet -m "data: hamburg delays $stamp" | Out-Null

    $push = RunGit push origin HEAD:main
    if ($LASTEXITCODE -eq 0) {
        Log "committed + pushed: $stamp (attempt $attempt)"
        $pushed = $true
        break
    }
    Log "push rejected (attempt $attempt), re-syncing: $push"
}

if (-not $pushed) {
    Log "could not push after 5 attempts - commit kept locally, next run retries"
    exit 1
}
