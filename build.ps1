param([switch]$Onedir)
$ErrorActionPreference = 'Stop'
$previousBuildMode = $env:DESKTOP_COWORKER_ONEDIR
Push-Location $PSScriptRoot
try {
    $buildPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    & $buildPython -c "import struct, sys; assert sys.platform == 'win32' and struct.calcsize('P') == 8, 'Build requires Windows x64 Python'"
    if ($LASTEXITCODE -ne 0) { throw 'Unsupported build platform' }
    if ($Onedir) {
        $env:DESKTOP_COWORKER_ONEDIR = '1'
        & $buildPython -m PyInstaller --clean --noconfirm --workpath build/work-onedir --distpath build/onedir DesktopCoworker.spec
    } else {
        $env:DESKTOP_COWORKER_ONEDIR = '0'
        & $buildPython -m PyInstaller --clean --noconfirm --workpath build/work-onefile --distpath dist DesktopCoworker.spec
    }
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
} finally {
    $env:DESKTOP_COWORKER_ONEDIR = $previousBuildMode
    Pop-Location
}
