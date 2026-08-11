# Bootstrap local (PowerShell) — espelho de bootstrap.sh no Windows nativo.
# Uso:
#   .\bootstrap.ps1
#   .\bootstrap.ps1 -Bg
#   .\bootstrap.ps1 -Down
#   .\bootstrap.ps1 -Check
# Preferência: ./bootstrap.sh no Git Bash se disponível.

param(
  [switch]$Bg,
  [switch]$NoCelery,
  [switch]$Down,
  [switch]$Check
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (Get-Command bash -ErrorAction SilentlyContinue) {
  $argsList = @()
  if ($Bg) { $argsList += "--bg" }
  if ($NoCelery) { $argsList += "--no-celery" }
  if ($Down) { $argsList += "--down" }
  if ($Check) { $argsList += "--check" }
  & bash "$Root/bootstrap.sh" @argsList
  exit $LASTEXITCODE
}

Write-Host "[bootstrap] bash não encontrado — modo PowerShell nativo" -ForegroundColor Yellow

function Ensure-Docker {
  docker info 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { return }
  $dd = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
  if (Test-Path $dd) {
    Write-Host "[bootstrap] Iniciando Docker Desktop..."
    Start-Process $dd
  }
  for ($i = 1; $i -le 36; $i++) {
    docker info 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { return }
    Start-Sleep -Seconds 5
  }
  throw "Docker não ficou pronto"
}

if ($Down) {
  Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -match 'manage.py runserver|celery -A config' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  docker compose down
  Write-Host "[bootstrap] ambiente parado"
  exit 0
}

if ($Check) {
  docker compose ps
  foreach ($u in @("http://127.0.0.1:8000/app/", "http://127.0.0.1:8000/hub/login/")) {
    try {
      $c = (Invoke-WebRequest -Uri $u -UseBasicParsing -TimeoutSec 5).StatusCode
      Write-Host "[bootstrap] OK $u ($c)"
    } catch {
      Write-Host "[bootstrap] FAIL $u"
    }
  }
  exit 0
}

Ensure-Docker
docker compose up -d
for ($i = 1; $i -le 30; $i++) {
  docker exec exeq_hub_db pg_isready -U exeq -d exeq_hub 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { break }
  Start-Sleep -Seconds 2
}
if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
  Copy-Item ".env.example" ".env"
  Write-Host "[bootstrap] .env criado a partir de .env.example"
}
python -m pip install -q -r requirements.txt
python manage.py migrate --noinput
python manage.py check

if ($Bg) {
  if (-not $NoCelery) {
    Start-Process python -ArgumentList "-m","celery","-A","config","worker","-l","info","-P","solo" -WorkingDirectory $Root -WindowStyle Hidden
    Start-Process python -ArgumentList "-m","celery","-A","config","beat","-l","info" -WorkingDirectory $Root -WindowStyle Hidden
  }
  Start-Process python -ArgumentList "manage.py","runserver","0.0.0.0:8000" -WorkingDirectory $Root -WindowStyle Hidden
  Start-Sleep -Seconds 3
  Write-Host "[bootstrap] Hub V4  http://127.0.0.1:8000/hub/"
  Write-Host "[bootstrap] SPA     http://127.0.0.1:8000/app/"
  Write-Host "[bootstrap] Admin   http://127.0.0.1:8000/admin/"
  exit 0
}

if (-not $NoCelery) {
  Start-Process python -ArgumentList "-m","celery","-A","config","worker","-l","info","-P","solo" -WorkingDirectory $Root -WindowStyle Hidden
  Start-Process python -ArgumentList "-m","celery","-A","config","beat","-l","info" -WorkingDirectory $Root -WindowStyle Hidden
}
Write-Host "[bootstrap] Hub V4  http://127.0.0.1:8000/hub/"
Write-Host "[bootstrap] runserver foreground..."
python manage.py runserver 0.0.0.0:8000
