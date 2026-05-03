# Build Ftp-Auto-Sync.exe (needs Python 3.10+ on PATH or env PYTHON=full\path\to\python.exe)
# Output: dist\Ftp-Auto-Sync.exe
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Resolve-PythonExe {
    if ($env:PYTHON) {
        return $env:PYTHON
    }
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        $exe = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($exe) {
            return $exe.Trim()
        }
    }
    foreach ($name in @("python", "python3")) {
        $c = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $c) {
            continue
        }
        $p = $c.Source
        if ($p -match "WindowsApps\\python") {
            continue
        }
        return $p
    }
    throw "Python not found. Install from https://www.python.org/downloads/ or set environment variable PYTHON to the full path of python.exe"
}

$PythonExe = Resolve-PythonExe
Write-Host ("Using: " + $PythonExe)

Write-Host "Installing dependencies..."
& $PythonExe -m pip install -q -r requirements.txt
& $PythonExe -m pip install -q "pyinstaller>=6.0" "pyinstaller-hooks-contrib"

Write-Host "Building Ftp-Auto-Sync.exe ..."
& $PythonExe -m PyInstaller --noconfirm --clean ftp_auto_sync.spec

$exe = Join-Path $PSScriptRoot "dist\Ftp-Auto-Sync.exe"
if (Test-Path $exe) {
    Write-Host ("OK: " + $exe)
    exit 0
} else {
    Write-Host "Build failed: EXE not found."
    exit 1
}
