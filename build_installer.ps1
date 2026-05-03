# EXE (PyInstaller) → Inno Setup インストーラーまで一括ビルド
# 前提: Inno Setup 6 https://jrsoftware.org/isdl.php
# 出力: release\Ftp-Auto-Sync_Setup_4.7.0.exe 等（バージョンは installer\FTPAutoSync.iss の #define に準拠）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

& "$PSScriptRoot\build.ps1"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$candidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    Write-Host ""
    Write-Host "Inno Setup 6 が見つかりません。次からインストールしてください:" -ForegroundColor Yellow
    Write-Host "  https://jrsoftware.org/isdl.php"
    Write-Host "EXE のみの成果物: dist\Ftp-Auto-Sync.exe"
    exit 2
}

Write-Host "Running Inno Setup compiler: $iscc"
& $iscc "$PSScriptRoot\installer\FTPAutoSync.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Inno Setup failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Get-ChildItem "$PSScriptRoot\release" -Filter "Ftp-Auto-Sync_Setup*.exe" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host ("OK (installer): " + $_.FullName)
}
