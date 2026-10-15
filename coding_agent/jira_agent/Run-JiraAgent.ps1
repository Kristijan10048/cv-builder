<# Start the recurring Jira implementation scheduler using the user's configuration. #>
[CmdletBinding()]
param(
    [string]$CodexExecutable,
    [string]$PythonExecutable,
    [switch]$Tickets,
    [switch]$Projects,
    [string]$Project
)

$ErrorActionPreference = 'Stop'
if ($Tickets -and $Projects) {
    throw 'Choose either -Tickets or -Projects.'
}
if ($Project -and -not $Tickets) {
    throw '-Project requires -Tickets.'
}
$workerArguments = @()
if ($Tickets) {
    $workerArguments += '--tickets'
    if ($Project) {
        $workerArguments += $Project
    }
}
if ($Projects) {
    $workerArguments += '--projects'
}
$settingNames = @(
    'JIRA_URL', 'JIRA_EMAIL', 'JIRA_API_TOKEN', 'JIRA_PROJECT',
    'JIRA_AGENT_REPOSITORY', 'JIRA_AGENT_CSV_PATH', 'AGENT_CMD', 'AGENT_TIMEOUT',
    'JIRA_STATUS', 'POLL_INTERVAL'
)

# Use saved settings as fallbacks while preserving this terminal's configuration.
foreach ($settingName in $settingNames) {
    $processSettingValue = [Environment]::GetEnvironmentVariable($settingName, 'Process')
    if (-not [string]::IsNullOrWhiteSpace($processSettingValue)) {
        continue
    }
    $settingValue = [Environment]::GetEnvironmentVariable($settingName, 'User')
    if (-not [string]::IsNullOrWhiteSpace($settingValue)) {
        [Environment]::SetEnvironmentVariable($settingName, $settingValue, 'Process')
    }
}

# Python validates required settings after applying the optional local .env fallback.

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not [string]::IsNullOrWhiteSpace($userPath)) {
    $env:Path = $env:Path + [IO.Path]::PathSeparator + $userPath
}

# The installer captures the executable path so a task does not depend on an old PATH.
if ([string]::IsNullOrWhiteSpace($env:AGENT_CMD) -and $CodexExecutable) {
    $env:AGENT_CMD = '"' + $CodexExecutable + '" --ask-for-approval never exec --sandbox workspace-write {prompt}'
}

$repositoryDirectory = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if ([string]::IsNullOrWhiteSpace($PythonExecutable)) {
    $PythonExecutable = Join-Path $repositoryDirectory '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    throw ('Python executable not found: ' + $PythonExecutable +
        '. Create the repository virtual environment or supply -PythonExecutable.')
}

$logDirectory = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logPath = Join-Path $logDirectory 'jira-agent.log'
Push-Location -LiteralPath $repositoryDirectory
$previousErrorActionPreference = $ErrorActionPreference
try {
    # Windows PowerShell treats native stderr as ErrorRecord objects. Allow the
    # process to finish so its complete traceback and real exit code are retained.
    $ErrorActionPreference = 'Continue'
    & $PythonExecutable -u (Join-Path $PSScriptRoot 'jira_agent.py') @workerArguments 2>&1 | ForEach-Object {
        $outputLine = $_.ToString()
        $outputLine | Out-File -LiteralPath $logPath -Append -Encoding utf8 -ErrorAction Stop
        Write-Host $outputLine
    }
    $workerExitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $previousErrorActionPreference
    Pop-Location
}
if ($workerExitCode -ne 0) {
    Write-Host ('Jira agent exited with code ' + $workerExitCode + '. Full output: ' + $logPath)
}
exit $workerExitCode
