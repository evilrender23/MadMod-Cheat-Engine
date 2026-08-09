$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (Test-Path build) { Remove-Item -Recurse -Force build }
if (Test-Path dist) { Remove-Item -Recurse -Force dist }

& .\scripts\test.ps1
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--windowed",
    "--name", "MemPilot",
    "--paths", "src",
    "--add-data", "assets;assets",
    "--collect-submodules", "mempilot",
    "--exclude-module", "PySide6.QtWebEngineCore",
    "--exclude-module", "PySide6.QtWebEngineWidgets",
    "--exclude-module", "PySide6.Qt3DCore",
    "--exclude-module", "PySide6.QtCharts",
    "--exclude-module", "PySide6.QtQuick3D",
    "--exclude-module", "tkinter",
    "--exclude-module", "matplotlib",
    "src/mempilot/__main__.py"
)
& .\.venv\Scripts\pyinstaller.exe @PyInstallerArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (Test-Path MemPilot.spec) { Remove-Item -Force MemPilot.spec }


$Executable = [System.IO.Path]::GetFullPath("dist\MemPilot\MemPilot.exe")
Write-Output $Executable
