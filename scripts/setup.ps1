$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Push-Location $repo
try {
    if (-not (Test-Path ".venv\Scripts\python.exe")) {
        python -m venv .venv
    }
    $python = Join-Path $repo ".venv\Scripts\python.exe"
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements.lock
    & $python -m pip install -e ".[dev]"
    Push-Location "apps\web"
    try {
        npm.cmd ci
    }
    finally {
        Pop-Location
    }
    Write-Host "S1 development dependencies installed."
}
finally {
    Pop-Location
}
