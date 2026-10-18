$ErrorActionPreference = "Stop"

$projectRoot = (
    Resolve-Path (Join-Path $PSScriptRoot "..\..")
).Path

$jobRunner = Join-Path `
    $projectRoot `
    "scripts\automation\run_marine_job.ps1"

if (-not (Test-Path $jobRunner)) {
    throw "Scheduled-job wrapper was not found: $jobRunner"
}

$powerShellExecutable = Join-Path `
    $env:SystemRoot `
    "System32\WindowsPowerShell\v1.0\powershell.exe"

$currentUser = (
    [System.Security.Principal.WindowsIdentity]::GetCurrent()
).Name

$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4)

function New-MarineTaskAction {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Job
    )

    $arguments = (
        "-NoProfile " +
        "-ExecutionPolicy Bypass " +
        "-File `"$jobRunner`" " +
        "-Job $Job"
    )

    return New-ScheduledTaskAction `
        -Execute $powerShellExecutable `
        -Argument $arguments `
        -WorkingDirectory $projectRoot
}

$now = Get-Date

$minutesUntilAis = 10 - ($now.Minute % 10)

$aisStart = $now.AddMinutes(
    $minutesUntilAis
).AddSeconds(
    -$now.Second
).AddMilliseconds(
    -$now.Millisecond
)

$minutesUntilWeather = 15 - ($now.Minute % 15)

$weatherStart = $now.AddMinutes(
    $minutesUntilWeather
).AddSeconds(
    -$now.Second
).AddMilliseconds(
    -$now.Millisecond
)

$nextOceanHour = (
    [Math]::Floor($now.Hour / 6) + 1
) * 6

if ($nextOceanHour -ge 24) {
    $oceanStart = $now.Date.AddDays(1)
}
else {
    $oceanStart = $now.Date.AddHours($nextOceanHour)
}

$retentionStart = $now.Date.AddHours(3).AddMinutes(30)

if ($retentionStart -le $now) {
    $retentionStart = $retentionStart.AddDays(1)
}

$aisTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At $aisStart `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$weatherTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At $weatherStart `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$oceanTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At $oceanStart `
    -RepetitionInterval (New-TimeSpan -Hours 6) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$retentionTrigger = New-ScheduledTaskTrigger `
    -Daily `
    -At $retentionStart

Register-ScheduledTask `
    -TaskName "MarineVerse-AIS-ETL" `
    -Description "Capture and load live AIS vessel data every 10 minutes." `
    -Action (New-MarineTaskAction -Job "ais") `
    -Trigger $aisTrigger `
    -Settings $settings `
    -Principal $principal `
    -Force |
    Out-Null

Register-ScheduledTask `
    -TaskName "MarineVerse-Weather-ETL" `
    -Description "Retrieve and load Open-Meteo port weather every 15 minutes." `
    -Action (New-MarineTaskAction -Job "weather") `
    -Trigger $weatherTrigger `
    -Settings $settings `
    -Principal $principal `
    -Force |
    Out-Null

Register-ScheduledTask `
    -TaskName "MarineVerse-Ocean-ETL" `
    -Description "Retrieve and load Copernicus ocean data every 6 hours." `
    -Action (New-MarineTaskAction -Job "ocean") `
    -Trigger $oceanTrigger `
    -Settings $settings `
    -Principal $principal `
    -Force |
    Out-Null

Register-ScheduledTask `
    -TaskName "MarineVerse-Retention-DryRun" `
    -Description "Evaluate marine data retention daily without deleting records." `
    -Action (New-MarineTaskAction -Job "retention-dry-run") `
    -Trigger $retentionTrigger `
    -Settings $settings `
    -Principal $principal `
    -Force |
    Out-Null

Write-Host "MarineVerse scheduled tasks registered."
Write-Host "AIS begins:       $aisStart"
Write-Host "Weather begins:   $weatherStart"
Write-Host "Ocean begins:     $oceanStart"
Write-Host "Retention begins: $retentionStart"
