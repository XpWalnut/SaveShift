param(
    [Parameter(Mandatory = $true)]
    [string]$Checkpoint,
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
    throw "Close Save Shift before restoring a rollout checkpoint."
}

Write-Host ""
Write-Host "This restores the exact Save Shift database and settings from:"
Write-Host $Checkpoint
Write-Host "A verified checkpoint of the current state will be created first."
Write-Host "Game save folders and Steam Workshop items are not deleted."
Write-Host ""
$Confirmation = Read-Host "Type ROLLBACK to continue"
if ($Confirmation -cne "ROLLBACK") {
    Write-Host "Cancelled. Nothing was changed."
    exit 0
}

Push-Location $ProjectRoot
try {
    & $Python ".\tools\rollout_checkpoint.py" restore `
        --checkpoint $Checkpoint `
        --data-directory $DataDirectory `
        --backup-root $BackupRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Rollout checkpoint restore failed."
    }
}
finally {
    Pop-Location
}
