# Smoke NF-e tenant ALE - Postgres, migrate, pytest, optional manage.py
#
# Uso (na raiz do repo):
#   .\scripts\smoke_nfe_ale.ps1
#   .\scripts\smoke_nfe_ale.ps1 -WithManagePy
#   .\scripts\smoke_nfe_ale.ps1 -WithManagePy -TpAmb 1
#   .\scripts\smoke_nfe_ale.ps1 -SkipDocker
#   .\scripts\smoke_nfe_ale.ps1 -SkipPytest -WithManagePy
#
# Requisitos: Docker Desktop, Python 3.11+, Postgres 127.0.0.1:5433

param(
  [switch]$SkipDocker,
  [switch]$SkipMigrate,
  [switch]$SkipPytest,
  [switch]$SkipInstall,
  [switch]$WithManagePy,
  [switch]$SkipSeed,
  [ValidateSet("1", "2")]
  [string]$TpAmb = "2",
  [switch]$VerbosePytest,
  [string]$EvidenceOut = ".storage/nfe_spike_ale_evidence.json"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Remove-Item Env:EXEQ_TEST_SQLITE -ErrorAction SilentlyContinue

function Write-Step([string]$Message) {
  Write-Host "[smoke-nfe-ale] $Message" -ForegroundColor Cyan
}

function Ensure-Docker {
  docker info 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { return }

  $dd = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
  if (Test-Path $dd) {
    Write-Step "Iniciando Docker Desktop..."
    Start-Process $dd
  }

  for ($i = 1; $i -le 36; $i++) {
    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return }
    Start-Sleep -Seconds 5
  }
  throw 'Docker nao ficou pronto - abra o Docker Desktop e tente novamente.'
}

function Wait-Postgres {
  Write-Step 'Aguardando Postgres (exeq_hub porta 5433)...'
  for ($i = 1; $i -le 30; $i++) {
    docker exec exeq_hub_db pg_isready -U exeq -d exeq_hub 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
      Write-Step "Postgres OK"
      return
    }
    Start-Sleep -Seconds 2
  }
  throw 'Postgres nao respondeu - verifique: docker compose ps; docker logs exeq_hub_db'
}

function Invoke-SeedAle {
  Write-Step 'Provisionando tenant ALE (idempotente)...'
  python "$Root\scripts\seed_ale_smoke.py"
  if ($LASTEXITCODE -ne 0) { throw "Seed ALE falhou (exit $LASTEXITCODE)" }
}

Write-Step "Repo: $Root"

if (-not $SkipDocker) {
  Ensure-Docker
  Write-Step "Subindo container db..."
  docker compose up -d db
  if ($LASTEXITCODE -ne 0) { throw "docker compose up -d db falhou" }
  Wait-Postgres
} else {
  Write-Step 'SkipDocker - assumindo Postgres em 127.0.0.1:5433'
}

if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
  Copy-Item ".env.example" ".env"
  Write-Step ".env criado a partir de .env.example"
}

if (-not $SkipInstall) {
  Write-Step "Instalando dependencias (requirements.txt)..."
  python -m pip install -q -r requirements.txt
}

if (-not $SkipMigrate) {
  Write-Step "migrate..."
  python manage.py migrate --noinput
  if ($LASTEXITCODE -ne 0) { throw "migrate falhou" }
}

if (-not $SkipPytest) {
  Write-Step "pytest smoke/homolog ALE..."
  $pytestArgs = @(
    "-m", "pytest",
    "apps/nfe/tests/test_smoke_e2e_ale.py",
    "apps/nfe/tests/test_homolog_spike.py",
    "-q",
    "--tb=short",
    "--reuse-db"
  )
  if ($VerbosePytest) { $pytestArgs += "-v" }
  python @pytestArgs
  if ($LASTEXITCODE -ne 0) { throw "pytest falhou (exit $LASTEXITCODE)" }
  Write-Step "pytest OK"
} else {
  Write-Step "SkipPytest"
}

if ($WithManagePy) {
  if (-not $SkipSeed) {
    Invoke-SeedAle
  }
  Write-Step "manage.py nfe_spike_ale_homolog --smoke-e2e (stub tpAmb=$TpAmb)..."
  python manage.py nfe_spike_ale_homolog `
    --smoke-e2e `
    --mode stub `
    --tp-amb $TpAmb `
    --out $EvidenceOut
  if ($LASTEXITCODE -ne 0) { throw "manage.py smoke falhou (exit $LASTEXITCODE)" }
  $evidencePath = Resolve-Path $EvidenceOut -ErrorAction SilentlyContinue
  Write-Step "manage.py OK - evidence: $evidencePath"
}

Write-Host "[smoke-nfe-ale] SMOKE NFE ALE PASS" -ForegroundColor Green
