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
    "--name", "M@D-Engine",
    "--icon", "assets\mad-mod-engine.ico",
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
if (Test-Path "M@D-Engine.spec") { Remove-Item -Force "M@D-Engine.spec" }


$Executable = [System.IO.Path]::GetFullPath("dist\M@D-Engine\M@D-Engine.exe")
Write-Output $Executable
