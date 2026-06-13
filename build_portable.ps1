$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dist = Join-Path $Root "dist"
$Build = Join-Path $Root "build"
$Release = Join-Path $Root "release"
$OutputZip = "C:\Users\31688\Documents\Codex\2026-06-13\new-chat-2\outputs\DopplerSpeedometer-portable.zip"

if (Test-Path $Build) {
    Remove-Item -Recurse -Force $Build
}
if (Test-Path $Dist) {
    Remove-Item -Recurse -Force $Dist
}
if (Test-Path $Release) {
    Remove-Item -Recurse -Force $Release
}

New-Item -ItemType Directory -Force -Path $Release | Out-Null

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name DopplerSpeedometer `
    --add-data "samples;samples" `
    run.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 打包失败。"
}

$PortableDir = Join-Path $Release "portable"
Copy-Item -Recurse -Force (Join-Path $Dist "DopplerSpeedometer") $PortableDir

$ZipPath = Join-Path $Release "DopplerSpeedometer-portable.zip"
if (Test-Path $ZipPath) {
    Remove-Item -Force $ZipPath
}
Compress-Archive -Path (Join-Path $PortableDir "*") -DestinationPath $ZipPath -Force
Copy-Item -Force $ZipPath $OutputZip

Write-Host "便携版已生成: $OutputZip"
