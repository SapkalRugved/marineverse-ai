param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("replay", "ibtracs", "ports", "weather")]
    [string]$Job,
    [string]$ConfigFile,
    [switch]$Execute
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Virtual-environment Python not found: $python" }
$logs = Join-Path $projectRoot "logs\platform"
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$log = Join-Path $logs ($Job + "_" + (Get-Date -Format "yyyyMMddTHHmmssfff") + ".log")

if ($Job -eq "replay") {
    if (-not $ConfigFile) { throw "Replay requires an explicit local job configuration." }
    $resolvedConfig = (Resolve-Path $ConfigFile).Path
    $arguments = @("-u", "-m", "backend.marine_data.platform.schedule", $resolvedConfig)
} else {
    $arguments = @("-u", "-m", "backend.marine_data.platform.refresh", $Job)
    if ($Execute) { $arguments += "--execute" }
}

Push-Location $projectRoot
try {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $python @arguments 2>&1 | ForEach-Object {
            $line = $_.ToString()
            Write-Host $line
            Add-Content -Path $log -Value $line -Encoding UTF8
        }
        $jobExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($jobExitCode -ne 0) { throw "Platform job failed with exit code $jobExitCode. See $log" }
} finally {
    Pop-Location
}
