<#
.SYNOPSIS
Run the independent CV Builder worker in the foreground, or validate its setup.
.DESCRIPTION
Uses the repository virtual environment and shared CV_BUILDER_* settings.
Does not install a Windows task or start the web server.
#>
[CmdletBinding()]
param(
    [string]$DatabasePath,
    [string]$LockDirectory,
    [string]$LogDirectory,
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$schedulerProjectRoot = Split-Path -Parent $PSScriptRoot
$schedulerPython = Join-Path $schedulerProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $schedulerPython -PathType Leaf)) {
    throw 'Project Python is missing. Create .venv and install requirements.txt first.'
}
$schedulerPreviousSettings = @{}
$schedulerOverrides = @{
    CV_BUILDER_DATABASE_PATH = $DatabasePath
    CV_BUILDER_LOCK_DIR = $LockDirectory
    CV_BUILDER_SCHEDULER_LOG_DIR = $LogDirectory
}
try {
    foreach ($schedulerSetting in $schedulerOverrides.Keys) {
        if ($schedulerOverrides[$schedulerSetting]) {
            $schedulerPreviousSettings[$schedulerSetting] = [Environment]::GetEnvironmentVariable($schedulerSetting, 'Process')
            [Environment]::SetEnvironmentVariable($schedulerSetting, $schedulerOverrides[$schedulerSetting], 'Process')
        }
    }
    Push-Location -LiteralPath $schedulerProjectRoot
    try {
        & $schedulerPython -c 'from app.scheduler.configuration import SchedulerConfiguration; from app.scheduler.runtime import SchedulerRuntime; SchedulerConfiguration.from_environment(); print("Scheduler configuration and imports OK.")'
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        if (-not $ValidateOnly) {
            & $schedulerPython -m app.scheduler
            exit $LASTEXITCODE
        }
    }
    finally { Pop-Location }
}
finally {
    foreach ($schedulerSetting in $schedulerPreviousSettings.Keys) {
        [Environment]::SetEnvironmentVariable($schedulerSetting, $schedulerPreviousSettings[$schedulerSetting], 'Process')
    }
}
