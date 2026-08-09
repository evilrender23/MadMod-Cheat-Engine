$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& $Python -c "import mempilot" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $Python -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

& $Python -m mempilot @args
exit $LASTEXITCODE
