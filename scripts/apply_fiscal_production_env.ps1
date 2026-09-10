# Perfil SEFAZ produção (tpAmb=1) — ajusta .env local (não versionado).
# Uso: .\scripts\apply_fiscal_production_env.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env"

if (-not (Test-Path $EnvFile)) {
  Copy-Item (Join-Path $Root ".env.example") $EnvFile
  Write-Host "[fiscal-prod] .env criado a partir de .env.example"
}

function Set-EnvLine([string]$Key, [string]$Value) {
  $pattern = "^\s*$([regex]::Escape($Key))\s*="
  $line = "$Key=$Value"
  $content = Get-Content $EnvFile -Raw
  if ($content -match "(?m)$pattern") {
    $content = [regex]::Replace($content, "(?m)$pattern.*", $line)
  } else {
    $content = $content.TrimEnd() + "`n$line`n"
  }
  Set-Content -Path $EnvFile -Value $content -NoNewline
}

Set-EnvLine "NFE_ENABLED" "true"
Set-EnvLine "NFE_HTTP_MODE" "http"
Set-EnvLine "NFE_HTTP_DRY_RUN" "false"
Set-EnvLine "NFE_DEFAULT_TP_AMB" "1"

Set-EnvLine "NFCE_ENABLED" "true"
Set-EnvLine "NFCE_HTTP_MODE" "http"
Set-EnvLine "NFCE_HTTP_DRY_RUN" "false"
Set-EnvLine "NFCE_DEFAULT_TP_AMB" "1"

Set-EnvLine "NFE_ENTRADA_ENABLED" "true"
Set-EnvLine "NFE_ENTRADA_HTTP_MODE" "http"
Set-EnvLine "NFE_ENTRADA_HTTP_DRY_RUN" "false"

Write-Host "[fiscal-prod] .env apontado para SEFAZ producao (tpAmb=1, HTTP real, dry_run=false)"
Write-Host "[fiscal-prod] Reinicie runserver/celery apos alteracao."
