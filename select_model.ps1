# select_model.ps1
$baseUrl = "http://192.168.1.179:1234/v1"

Write-Host "Fetching available models from $baseUrl..." -ForegroundColor Cyan
try {
    $json = curl.exe "$baseUrl/models" | ConvertFrom-Json
    if ($json.data) {
        $models = $json.data | ForEach-Object { $_.id }
    } else {
        $models = $json | ForEach-Object { $_.id }
    }
} catch {
    Write-Host "Failed to fetch models from $baseUrl" -ForegroundColor Red
    Pause
    exit
}

$models = $models | Where-Object { $_ -ne $null -and $_ -ne "" } | Select-Object -Unique

if ($null -eq $models) {
    Write-Host "No models found in configuration file." -ForegroundColor Red
    Pause
    exit
}

Write-Host "--- Copilot Model Selection ---" -ForegroundColor Cyan
for ($i = 0; $i -lt $models.Count; $i++) {
    Write-Host ("{0}. {1}" -f ($i + 1), $models[$i])
}

$choice = Read-Host "`nSelect a model (number)"
if ($choice -as [int] -and [int]$choice -gt 0 -and [int]$choice -le $models.Count) {
    $selectedModel = $models[[int]$choice - 1]
    Write-Host "Selected: $selectedModel" -ForegroundColor Green
    
    # Set environment variables for the current session and child processes
    $env:COPILOT_PROVIDER_BASE_URL = $baseUrl
    $env:COPILOT_PROVIDER_TYPE = "openai"
    $env:COPILOT_MODEL = $selectedModel
    $env:COPILOT_OFFLINE = "true"

    Write-Host "Launching Copilot..." -ForegroundColor Cyan
    # Execute the copilot binary
    Start-Process "copilot.exe"
}
else {
    Write-Host "Invalid selection. Please restart the script." -ForegroundColor Red
    Pause
}