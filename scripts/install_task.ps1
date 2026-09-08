<#
    Register a Windows Scheduled Task that runs collect_and_push.ps1 every 15
    minutes while you are logged in. Run this once, from an ordinary
    (non-admin) PowerShell:

        powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1

    Remove it later with:  Unregister-ScheduledTask -TaskName "HamburgDelaysCollector"
#>
param(
    [string]$TaskName = "HamburgDelaysCollector",
    [int]$IntervalMinutes = 15
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot "collect_and_push.ps1"

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`"" `
    -WorkingDirectory $repo

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Polls the DB Timetables API for Hamburg Hbf arrivals and pushes hamburg_delays.csv." `
    -Force

Write-Host "Registered '$TaskName' - runs every $IntervalMinutes min." -ForegroundColor Green
Write-Host "First run starts now. Check collector.log in $repo"
