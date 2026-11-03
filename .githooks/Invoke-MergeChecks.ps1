param(
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$C_ProjectRelativePath = '.'
$C_JavaScriptDirectories = @('static', 'firefox-extension')

try {
    $repositoryRoot = (& git rev-parse --show-toplevel)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repositoryRoot)) {
        throw 'Could not locate the Git repository root.'
    }

    $projectDirectory = Join-Path $repositoryRoot $C_ProjectRelativePath
    if (-not (Test-Path -LiteralPath $projectDirectory -PathType Container)) {
        throw "Project directory does not exist: $projectDirectory"
    }

    $changedProjectFiles = @(& git diff --cached --name-only -- $C_ProjectRelativePath)
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not inspect the staged merge changes.'
    }

    if (-not $Force -and $changedProjectFiles.Count -eq 0) {
        Write-Host 'CV Builder merge checks: no project files changed; skipping.'
        exit 0
    }

    Write-Host 'CV Builder merge checks: staged whitespace'
    & git diff --cached --check -- $C_ProjectRelativePath
    if ($LASTEXITCODE -ne 0) {
        throw 'Staged whitespace check failed.'
    }

    $pythonExecutable = Join-Path $projectDirectory '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $pythonExecutable -PathType Leaf)) {
        throw "Project Python executable is missing: $pythonExecutable"
    }

    Push-Location -LiteralPath $projectDirectory
    try {
        Write-Host 'CV Builder merge checks: Python tests'
        & $pythonExecutable -m pytest -q
        if ($LASTEXITCODE -ne 0) {
            throw 'Python tests failed.'
        }

        $nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
        if ($null -eq $nodeCommand) {
            throw 'Node.js is required to check JavaScript syntax.'
        }

        Write-Host 'CV Builder merge checks: JavaScript syntax'
        foreach ($directoryName in $C_JavaScriptDirectories) {
            $javaScriptDirectory = Join-Path $projectDirectory $directoryName
            $javaScriptFiles = Get-ChildItem -LiteralPath $javaScriptDirectory -Recurse -File -Filter '*.js'
            foreach ($javaScriptFile in $javaScriptFiles) {
                & $nodeCommand.Source --check $javaScriptFile.FullName
                if ($LASTEXITCODE -ne 0) {
                    throw "JavaScript syntax check failed: $($javaScriptFile.FullName)"
                }
            }
        }
    }
    finally {
        Pop-Location
    }

    Write-Host 'CV Builder merge checks passed.'
    exit 0
}
catch {
    Write-Error "CV Builder merge checks blocked the commit: $($_.Exception.Message)"
    exit 1
}
