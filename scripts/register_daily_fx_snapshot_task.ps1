param(
    [string]$TaskName = "Billing-DailyFxSnapshotSync",
    [string]$RunAt = "09:35",
    [string]$PythonExe = "python",
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$ScriptPath = Join-Path $ProjectRoot "scripts\sync_daily_fx_snapshot.py"
if (-not (Test-Path $ScriptPath)) {
    throw "Sync script not found: $ScriptPath"
}

$ActionArgs = "`"$ScriptPath`""
$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument $ActionArgs -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At $RunAt
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Sync daily FX snapshot state for billing service" `
    -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName"
Write-Host "Run time: $RunAt"
Write-Host "Python: $PythonExe"
Write-Host "Script: $ScriptPath"
