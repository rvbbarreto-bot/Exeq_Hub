# ADR-LAB-DB-001 — Gate SQLite (decisão PO)

| Campo | Valor |
|-------|--------|
| Status | **Aprovado PO** (2026-09-08) |
| Decisão | Lab/Hub **sempre Postgres**; SQLite **somente pytest offline** |

## Contexto

`EXEQ_TEST_SQLITE=1` no terminal ou `.env` fazia `runserver`/`shell` apontarem para `.storage/pytest_exeq.sqlite3`, divergindo do Postgres do `docker compose`. Isso causou login e guias DAS em bancos diferentes.

## Decisão

1. **`EXEQ_TEST_SQLITE=1` só é aceito dentro de `pytest`** — fora disso, `ImproperlyConfigured` na carga de `config.settings`.
2. **Não colocar** `EXEQ_TEST_SQLITE` no `.env` de lab.
3. **`bootstrap.sh` / `bootstrap.ps1`** removem a variável ao subir o ambiente.

## Uso permitido

```bash
# CI/dev offline sem Docker
EXEQ_TEST_SQLITE=1 python -m pytest apps/das/tests/ -q

# Lab normal (Hub, migrate, shell)
docker compose up -d
./bootstrap.sh --bg
```

## Implementação

- `config/db_gate.py` — `assert_sqlite_allowed()`
- `config/settings.py` — gate antes de `DATABASES`
- `config/tests/test_db_gate.py` — regressão
