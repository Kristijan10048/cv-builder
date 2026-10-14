<# Run one Jira implementation batch using the scheduled user's configuration. #>
[CmdletBinding()]
param([string]$CodexExecutable)

$ErrorActionPreference = 'Stop'
$settingNames = @(
    'JIRA_URL', 'JIRA_EMAIL', 'JIRA_API_TOKEN', 'JIRA_PROJECT',
    'JIRA_AGENT_REPOSITORY', 'JIRA_AGENT_CSV_PATH', 'AGENT_CMD', 'AGENT_TIMEOUT'
)

# Refresh persistent settings because Task Scheduler may have an older environment.
foreach ($settingName in $settingNames) {
    $settingValue = [Environment]::GetEnvironmentVariable($settingName, 'User')
    if (-not [string]::IsNullOrWhiteSpace($settingValue)) {
        [Environment]::SetEnvironmentVariable($settingName, $settingValue, 'Process')
    }
}

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not [string]::IsNullOrWhiteSpace($userPath)) {
    $env:Path = $env:Path + [IO.Path]::PathSeparator + $userPath
}

# The installer captures the executable path so a task does not depend on an old PATH.
if ([string]::IsNullOrWhiteSpace($env:AGENT_CMD) -and $CodexExecutable) {
    $env:AGENT_CMD = '"' + $CodexExecutable + '" --ask-for-approval never exec --sandbox workspace-write {prompt}'
}

$pythonExecutable = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
    throw 'The repository Python virtual environment is missing.'
}

$logDirectory = Join-Path $PSScriptRoot 'logs'
New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
$logPath = Join-Path $logDirectory 'jira-agent.log'
Push-Location -LiteralPath $PSScriptRoot
try {
    & $pythonExecutable (Join-Path $PSScriptRoot 'jira_agent.py') *>> $logPath
    $workerExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $workerExitCode
