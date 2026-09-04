[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$SteamUsername,

    [string]$SteamworksSdkPath = $(
        if ($env:STEAMWORKS_SDK_PATH) {
            $env:STEAMWORKS_SDK_PATH
        }
        else {
            Join-Path $HOME "sdk"
        }
    ),

    [string]$ContentRoot,
    [string]$ConfigurationRoot,
    [switch]$SkipBuild,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$AppId = "5096900"
$DepotId = "5096901"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

if (-not $ContentRoot) {
    $ContentRoot = Join-Path $ProjectRoot "dist\SaveShift"
}

if (-not $ConfigurationRoot) {
    $ConfigurationRoot = Join-Path $ProjectRoot "build\steampipe"
}

$ContentRoot = [System.IO.Path]::GetFullPath($ContentRoot)
$ConfigurationRoot = [System.IO.Path]::GetFullPath($ConfigurationRoot)
$SteamworksSdkPath = [System.IO.Path]::GetFullPath($SteamworksSdkPath)
$SteamCmd = Join-Path $SteamworksSdkPath "tools\ContentBuilder\builder\steamcmd.exe"
$ReleaseBuildScript = Join-Path $PSScriptRoot "build_release.ps1"
$SaveShiftExecutable = Join-Path $ContentRoot "SaveShift.exe"
$DevelopmentAppIdFile = Join-Path $ContentRoot "steam_appid.txt"
$DistributionMarker = Join-Path $ContentRoot "saveshift-distribution.txt"

Write-Host ""
Write-Host "====================================="
Write-Host " Save Shift Steam Build Upload"
Write-Host "====================================="
Write-Host ""

if (-not (Test-Path -LiteralPath $SteamCmd -PathType Leaf)) {
    throw "SteamCMD was not found at '$SteamCmd'. Set STEAMWORKS_SDK_PATH to the Steamworks SDK folder."
}

if (-not $SkipBuild) {
    Write-Host "Step 1 of 2: Building and testing Save Shift..."
    & $ReleaseBuildScript

    if ($LASTEXITCODE -ne 0) {
        throw "The Save Shift release build failed. Nothing was uploaded to Steam."
    }
}
else {
    Write-Host "Step 1 of 2: Reusing the existing Save Shift build."
}

if (-not (Test-Path -LiteralPath $SaveShiftExecutable -PathType Leaf)) {
    throw "The Steam build is missing '$SaveShiftExecutable'. Run without -SkipBuild to create it."
}

if (Test-Path -LiteralPath $DevelopmentAppIdFile) {
    throw "The development-only steam_appid.txt file is inside the Steam build and must be removed before uploading."
}

New-Item -ItemType Directory -Path $ConfigurationRoot -Force | Out-Null
$BuildOutput = Join-Path $ConfigurationRoot "output"
New-Item -ItemType Directory -Path $BuildOutput -Force | Out-Null

$DepotConfigPath = Join-Path $ConfigurationRoot "depot_build_$DepotId.vdf"
$AppConfigPath = Join-Path $ConfigurationRoot "app_build_$AppId.vdf"

$DepotConfig = @"
"DepotBuildConfig"
{
    "DepotID" "$DepotId"
    "ContentRoot" "$ContentRoot"

    "FileMapping"
    {
        "LocalPath" "*"
        "DepotPath" "."
        "recursive" "1"
    }

    "FileExclusion" "steam_appid.txt"
    "FileExclusion" "*.pdb"
    "FileExclusion" "*.log"
}
"@

$AppConfig = @"
"AppBuild"
{
    "AppID" "$AppId"
    "Desc" "Save Shift private cross-machine test"
    "BuildOutput" "$BuildOutput"
    "ContentRoot" "$ContentRoot"

    "Depots"
    {
        "$DepotId" "$DepotConfigPath"
    }
}
"@

Set-Content -LiteralPath $DepotConfigPath -Value $DepotConfig -Encoding ASCII
Set-Content -LiteralPath $AppConfigPath -Value $AppConfig -Encoding ASCII

Write-Host "Step 2 of 2: Uploading the built application to Steam..."
Write-Host "Application: $AppId"
Write-Host "Windows depot: $DepotId"
Write-Host "Files: $ContentRoot"
Write-Host ""

if ($DryRun) {
    Write-Host "Dry run complete. SteamCMD was not started and nothing was uploaded."
    Write-Host "Generated configuration: $ConfigurationRoot"
    exit 0
}

Write-Host "SteamCMD may ask for your Steam password and Steam Guard code."
Write-Host "Your credentials are entered directly into SteamCMD and are not stored by this script."
Write-Host ""

Set-Content -LiteralPath $DistributionMarker -Value "steam" -Encoding ASCII

try {
    & $SteamCmd `
        "+login" $SteamUsername `
        "+run_app_build" $AppConfigPath `
        "+quit"

    if ($LASTEXITCODE -ne 0) {
        throw "SteamCMD failed. Review its output above; the Steam build was not completed."
    }
}
finally {
    Remove-Item -LiteralPath $DistributionMarker -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "====================================="
Write-Host " Steam Upload Complete"
Write-Host "====================================="
Write-Host ""
Write-Host "Next: open Steamworks > SteamPipe > Builds and refresh the page."
Write-Host "The uploaded build should now be listed there."
