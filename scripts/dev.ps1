param([switch]$Down)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $repo ".env"
if (-not (Test-Path $envFile)) {
    throw "Missing .env. Copy .env.example to .env and replace every CHANGE_ME value."
}
Push-Location $repo
try {
    if ($Down) {
        docker compose --env-file .env -f infra/compose/compose.yaml down
    }
    else {
        docker compose --env-file .env -f infra/compose/compose.yaml up --build
    }
}
finally {
    Pop-Location
}
