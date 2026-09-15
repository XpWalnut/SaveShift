param(
    [string]$Label = "pre-alpha.4",
    [string]$DataDirectory = "$HOME\.saveshift\data",
    [string]$BackupRoot = "$HOME\.saveshift\backups\rollout"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "The project Python environment was not found at $Python."
}
if (Get-Process -Name "SaveShift" -ErrorAction SilentlyContinue) {
    throw "Close Save Shift before creating a rollout checkpoint."
}

Push-Location $ProjectRoot
try {
    & $Python ".\tools\rollout_checkpoint.py" create `
        --data-directory $DataDirectory `
        --backup-root $BackupRoot `
        --label $Label
    if ($LASTEXITCODE -ne 0) {
        throw "Rollout checkpoint creation failed."
    }
}
finally {
    Pop-Location
}
