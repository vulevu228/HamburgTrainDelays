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

    The reset happens in a PRIVATE worktree (%LOCALAPPDATA%\HamburgTrainDelays-collector),
    never in the folder you work in: that folder also holds the Power BI project, and a
    reset --hard there would silently undo unsaved report edits every 15 minutes.
    After a push, your folder only fast-forwards (never discards local changes).
#>
param(
    [string]$Python = "python"
)

# git writes progress to stderr; don't let that abort the script
$ErrorActionPreference = "Continue"
$main = Split-Path -Parent $PSScriptRoot
$work = Join-Path $env:LOCALAPPDATA "HamburgTrainDelays-collector"

$log = Join-Path $main "collector.log"
function Log($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), ($msg -join " ")
    Add-Content -Path $log -Value $line -Encoding utf8
}
function RunGit { (& git.exe @args 2>&1) -join " " }

if (-not (Test-Path (Join-Path $work ".git"))) {
    RunGit -C $main fetch --quiet origin main | Out-Null
    $out = RunGit -C $main worktree add --detach $work origin/main
    Log "created collector worktree: $out"
}
# hamburg_collector.py loads .env from its own folder tree
Copy-Item (Join-Path $main ".env") (Join-Path $work ".env") -Force
Set-Location $work

$pushed = $false
for ($attempt = 1; $attempt -le 5; $attempt++) {
    RunGit fetch --quiet origin main | Out-Null
    RunGit reset --hard --quiet origin/main | Out-Null

    $out = & $Python (Join-Path $work "scripts\hamburg_collector.py") 2>&1
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
    # Commit under a bot identity not linked to any GitHub account, so these
    # ~96 automated commits/day don't flood the owner's contribution graph.
    RunGit -c user.name="hamburg-delays-collector" -c user.email="collector@hamburg-delays.local" commit --quiet -m "data: hamburg delays $stamp" | Out-Null

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

# Bring the new data into your working folder. --ff-only never overwrites local
# changes; if the folder has diverged or the CSV was edited, it just logs and waits.
$ff = RunGit -C $main merge --ff-only --quiet origin/main
if ($LASTEXITCODE -ne 0) { Log "working folder not fast-forwarded (local changes?): $ff" }
