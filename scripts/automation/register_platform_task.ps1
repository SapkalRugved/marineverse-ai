param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("replay", "ibtracs", "ports", "weather")]
    [string]$Job,
    [string]$ConfigFile,
    [ValidatePattern('^\d{2}:\d{2}$')]
    [string]$At = "03:30",
    [switch]$Execute
)

$ErrorActionPreference = "Stop"
$runner = Join-Path $PSScriptRoot "run_platform_job.ps1"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
if ($Job -eq "replay" -and -not $ConfigFile) { throw "Replay requires ConfigFile." }
if ($ConfigFile) { $ConfigFile = (Resolve-Path $ConfigFile).Path }
$time = [DateTime]::ParseExact($At, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
$arguments = '-NoProfile -File "' + $runner + '" -Job ' + $Job
if ($Job -eq "replay") {
    $arguments += ' -ConfigFile "' + $ConfigFile + '"'
} else {
    $arguments += ' -Execute'
}
$taskName = "MarineVerse-Platform-" + $Job
if (-not $Execute) {
    Write-Host "PREVIEW: daily task $taskName at local time $At"
    Write-Host "powershell.exe $arguments"
    Write-Host "Re-run with -Execute to register this task."
    exit 0
}
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)
# Current interactive user only; no elevation, stored password, or existing-task overwrite.
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "MarineVerse real-data platform daily $Job" | Out-Null
