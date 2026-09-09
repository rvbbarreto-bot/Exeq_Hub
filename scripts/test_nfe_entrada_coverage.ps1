# Suíte NF-e entrada — cobertura mínima 80% em apps.nfe.entrada
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

python -m pytest `
  apps/nfe/tests/test_entrada_api.py `
  apps/nfe/tests/test_entrada_artifacts.py `
  apps/nfe/tests/test_entrada_cursor.py `
  apps/nfe/tests/test_entrada_distribuicao.py `
  apps/nfe/tests/test_entrada_document_service.py `
  apps/nfe/tests/test_entrada_feature.py `
  apps/nfe/tests/test_entrada_integration.py `
  apps/nfe/tests/test_entrada_listing.py `
  apps/nfe/tests/test_entrada_manifestacao.py `
  apps/nfe/tests/test_entrada_models.py `
  apps/nfe/tests/test_entrada_openapi.py `
  apps/nfe/tests/test_entrada_schedule.py `
  apps/nfe/tests/test_entrada_serializers.py `
  apps/nfe/tests/test_entrada_system.py `
  apps/nfe/tests/test_entrada_tasks.py `
  apps/hub_v4/tests/test_nfe_entrada_hub.py `
  apps/hub_v4/tests/test_nfe_entrada_hub_ui.py `
  --cov=apps.nfe.entrada `
  --cov-report=term-missing `
  --cov-fail-under=80 `
  -q
