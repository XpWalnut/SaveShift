param(
    [string]$DatabasePath = "$HOME\.saveshift\data\saveshift.sqlite3",
    [string]$BackupDirectory = "$HOME\.saveshift\backups\database"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "The project Python environment was not found at $Python."
}

if (Get-Process -Name "SaveShift" -ErrorAction SilentlyContinue) {
    throw "Close Save Shift before downgrading its database."
}

Write-Host ""
Write-Host "This will return your Save Shift database to develop schema 3."
Write-Host "Database: $DatabasePath"
Write-Host "A verified backup will be written to: $BackupDirectory"
Write-Host "Only schema-4 group associations are removed; saves and history remain."
Write-Host ""
$Confirmation = Read-Host "Type DOWNGRADE to continue"
if ($Confirmation -cne "DOWNGRADE") {
    Write-Host "Cancelled. The database was not changed."
    exit 0
}

Push-Location $ProjectRoot
try {
    & $Python ".\tools\downgrade_database_to_develop.py" `
        --database $DatabasePath `
        --backup-directory $BackupDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Database downgrade failed."
    }
}
finally {
    Pop-Location
}
