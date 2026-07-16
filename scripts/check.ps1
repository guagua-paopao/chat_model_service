param([switch]$OnlineAudit)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv. Run scripts/setup.ps1 first."
}

Push-Location $repo
try {
    $env:PYTHONPATH = "$repo\apps\api\src"
    & $python -m compileall -q apps/api/src apps/api/scripts apps/fake-idp/src apps/worker/src tests
    & $python -m ruff check apps/api/src apps/api/scripts apps/fake-idp/src tests
    & $python -m mypy apps/api/src apps/fake-idp/src
    & $python -m pytest -W error --cov=qa_api --cov=fake_idp --cov-fail-under=85 --cov-report=term

    New-Item -ItemType Directory -Force ".local" | Out-Null
    $migrationDirectory = (Resolve-Path ".local").Path
    $migrationDb = Join-Path $migrationDirectory "migration-check.db"
    if (Test-Path -LiteralPath $migrationDb) { Remove-Item -LiteralPath $migrationDb }
    $env:QA_DATABASE_URL = "sqlite+pysqlite:///$($migrationDb -replace '\\','/')"
    & $python -m alembic -c alembic.ini upgrade head
    & $python -m alembic -c alembic.ini downgrade base
    & $python -m alembic -c alembic.ini upgrade head
    & $python -c "import yaml; p=yaml.safe_load(open('docs/enterprise-qa-system/openapi.yaml',encoding='utf-8')); assert p['openapi']=='3.1.0'; assert all(x in p['paths'] for x in ['/me','/models','/chat/completions','/messages/{message_id}/retry'])"

    Push-Location "apps\web"
    try {
        $env:NEXT_TELEMETRY_DISABLED = "1"
        npm.cmd run lint
        npm.cmd run typecheck
        npm.cmd run build
        if ($OnlineAudit) {
            npm.cmd audit --audit-level=moderate --registry=https://registry.npmjs.org
        }
    }
    finally {
        Pop-Location
    }

    $env:POSTGRES_DB = "enterprise_qa"
    $env:POSTGRES_USER = "enterprise_qa"
    $env:POSTGRES_PASSWORD = "local-validation-password"
    $env:REDIS_PASSWORD = "local-validation-password"
    $env:MINIO_ROOT_USER = "local-validation-user"
    $env:MINIO_ROOT_PASSWORD = "local-validation-password"
    $env:QA_OIDC_ISSUER = "https://dev-idp.invalid/"
    $env:QA_OIDC_AUDIENCE = "enterprise-qa-api"
    $env:QA_DEV_JWT_SECRET = "local-validation-jwt-secret-at-least-32-characters"
    $env:QA_CURSOR_SIGNING_KEY = "local-validation-cursor-key-at-least-32-characters"
    New-Item -ItemType Directory -Force ".local\docker-config" | Out-Null
    $env:DOCKER_CONFIG = (Resolve-Path ".local\docker-config").Path
    docker compose -f infra/compose/compose.yaml config --quiet

    $helm = Get-Command helm -ErrorAction SilentlyContinue
    if ($helm) { helm lint infra/helm/qa-system }
    else { Write-Warning "Helm is not installed; Helm lint was skipped." }

    if ($OnlineAudit) {
        & $python -m pip_audit -r requirements.lock
    }
    Write-Host "S2 checks passed."
}
finally {
    Pop-Location
}
