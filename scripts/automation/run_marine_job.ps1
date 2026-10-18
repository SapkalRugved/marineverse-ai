param(
    [Parameter(Mandatory = $true)]
    [ValidateSet(
        "weather",
        "ocean",
        "ais",
        "retention-dry-run"
    )]
    [string]$Job
)

$ErrorActionPreference = "Stop"

$projectRoot = (
    Resolve-Path (Join-Path $PSScriptRoot "..\..")
).Path

$pythonExecutable = Join-Path `
    $projectRoot `
    ".venv\Scripts\python.exe"

$logDirectory = Join-Path $projectRoot "logs\automation"

if (-not (Test-Path $pythonExecutable)) {
    throw "Virtual-environment Python was not found: $pythonExecutable"
}

New-Item `
    -ItemType Directory `
    -Path $logDirectory `
    -Force |
    Out-Null

$timestamp = Get-Date -Format "yyyyMMddTHHmmss"
$logPath = Join-Path `
    $logDirectory `
    "$($Job)_$timestamp.log"

$moduleArguments = switch ($Job) {
    "weather" {
        @(
            "-u",
            "-m",
            "backend.marine_data.automation.runner",
            "weather"
        )
    }

    "ocean" {
        @(
            "-u",
            "-m",
            "backend.marine_data.automation.runner",
            "ocean"
        )
    }

    "ais" {
        @(
            "-u",
            "-m",
            "backend.marine_data.automation.runner",
            "ais"
        )
    }

    "retention-dry-run" {
        @(
            "-u",
            "-m",
            "backend.marine_data.automation.retention"
        )
    }
}

function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Write-Host $Message

    Add-Content `
        -Path $logPath `
        -Value $Message `
        -Encoding UTF8
}

$exitCode = 0

Push-Location $projectRoot

try {
    Write-Log "Job: $Job"
    Write-Log (
        "Started at: " +
        [DateTimeOffset]::Now.ToString("o")
    )

    $previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"

try {
    & $pythonExecutable @moduleArguments 2>&1 |
        ForEach-Object {
            Write-Log $_.ToString()
        }

    $pythonExitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
}

    if ($pythonExitCode -ne 0) {
        throw "MarineVerse job exited with code $pythonExitCode."
    }

    Write-Log (
        "Completed at: " +
        [DateTimeOffset]::Now.ToString("o")
    )
}
catch {
    $exitCode = 1
    Write-Log "FAILED: $($_.Exception.Message)"
}
finally {
    Pop-Location
}

exit $exitCode
