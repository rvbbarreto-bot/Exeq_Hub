# Comparacao visual DANFE EXEQ vs PDFs de referencia (Desktop/PDFS)
#
# Uso:
#   .\scripts\compare_danfe_reference.ps1
#   .\scripts\compare_danfe_reference.ps1 -RefDir "C:\caminho\PDFS"
#   .\scripts\compare_danfe_reference.ps1 -OpenReport

param(
  [string]$RefDir = "",
  [string]$OutDir = ".storage/danfe_visual_compare",
  [int]$Dpi = 150,
  [switch]$OpenReport
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$argsList = @("scripts/compare_danfe_reference.py", "--out", $OutDir, "--dpi", $Dpi)
if ($RefDir) {
  $argsList += @("--ref-dir", $RefDir)
}

python @argsList
if ($LASTEXITCODE -ne 0) { throw "compare_danfe_reference falhou (exit $LASTEXITCODE)" }

$html = Join-Path -Path $Root -ChildPath (Join-Path -Path ($OutDir -replace '/', '\') -ChildPath "index.html")
Write-Host "[compare-danfe] OK - abra: $html" -ForegroundColor Green

if ($OpenReport -and (Test-Path $html)) {
  Start-Process $html
}
