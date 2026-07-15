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

Write-Host ""
Write-Host "============================="
Write-Host " Bundling Coordination Provider"
Write-Host "============================="
Write-Host ""

Push-Location ".\coordination\cloudflare"
try {
    pnpm install --frozen-lockfile

    if ($LASTEXITCODE -ne 0) {
        throw "Coordination dependencies could not be installed."
    }

    pnpm run typecheck

    if ($LASTEXITCODE -ne 0) {
        throw "Coordination provider type-check failed."
    }

    pnpm test

    if ($LASTEXITCODE -ne 0) {
        throw "Coordination provider tests failed."
    }

    pnpm run bundle

    if ($LASTEXITCODE -ne 0) {
        throw "Coordination provider bundle failed."
    }
}
finally {
    Pop-Location
}

Remove-Item ".\build" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item ".\dist\SaveShift" -Recurse -Force -ErrorAction SilentlyContinue

pyinstaller SaveShift.spec

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed."
}

$InnoCompiler = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
$InstallerScript = Join-Path $ProjectRoot "installer\SaveShift.iss"
$VersionValues = python -c "from app.version import APP_VERSION, APP_VERSION_INFO; print(f'{APP_VERSION}|{APP_VERSION_INFO}')"

if ($LASTEXITCODE -ne 0) {
    throw "Could not read the Save Shift version."
}

$AppVersion, $AppVersionInfo = $VersionValues.Trim().Split("|")

if (-not (Test-Path $InnoCompiler)) {
    throw "Inno Setup compiler was not found at: $InnoCompiler"
}

if (-not (Test-Path $InstallerScript)) {
    throw "Installer script was not found at: $InstallerScript"
}

& $InnoCompiler "/DAppVersion=$AppVersion" "/DAppVersionInfo=$AppVersionInfo" $InstallerScript

if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed."
}

Write-Host ""
Write-Host "============================="
Write-Host " Build Complete!"
Write-Host "============================="
Write-Host ""
Write-Host "Installer:"
Write-Host "$ProjectRoot\dist\installer\SaveShiftSetup-$AppVersion.exe"
