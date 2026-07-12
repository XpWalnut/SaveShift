$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host ""
Write-Host "============================="
Write-Host " Building Save Shift"
Write-Host "============================="
Write-Host ""

Write-Host ""
Write-Host "============================="
Write-Host " Running Regression Tests"
Write-Host "============================="
Write-Host ""

python -m pytest .\tests -q

if ($LASTEXITCODE -ne 0) {
    throw "Regression tests failed. Release build aborted."
}

Remove-Item ".\build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item ".\dist\SaveShift" -Recurse -Force -ErrorAction SilentlyContinue

pyinstaller SaveShift.spec

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed."
}

$InnoCompiler = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
$InstallerScript = Join-Path $ProjectRoot "installer\SaveShift.iss"

if (-not (Test-Path $InnoCompiler)) {
    throw "Inno Setup compiler was not found at: $InnoCompiler"
}

if (-not (Test-Path $InstallerScript)) {
    throw "Installer script was not found at: $InstallerScript"
}

& $InnoCompiler $InstallerScript

if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed."
}

Write-Host ""
Write-Host "============================="
Write-Host " Build Complete!"
Write-Host "============================="
Write-Host ""
Write-Host "Installer:"
Write-Host "$ProjectRoot\dist\installer\SaveShiftSetup-0.1.0-alpha.exe"