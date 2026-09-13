"""Provisiona tenant ALE para smoke NF-e (idempotente). Uso: python scripts/seed_ale_smoke.py"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from apps.accounts.models import Tenant
from apps.master_data.models import Customer, Provider, TaxRegime

CNPJ = "61536366000174"


def main() -> int:
    tenant, _ = Tenant.objects.get_or_create(
        slug="ALE",
        defaults={
            "legal_name": "ALE Piloto",
            "document": CNPJ,
            "settings": {"nfe_enabled": True},
        },
    )
    provider, created_p = Provider.objects.get_or_create(
        tenant=tenant,
        document=CNPJ,
        defaults={
            "legal_name": "ALE Emitente",
            "tax_regime": TaxRegime.SIMPLES,
            "state_registration": "123456789112",
            "address": {
                "logradouro": "Rua Piloto",
                "numero": "100",
                "bairro": "Centro",
                "municipio": "Atibaia",
                "uf": "SP",
                "cep": "12942480",
                "codigo_ibge": "3504107",
            },
        },
    )
    customer, created_c = Customer.objects.get_or_create(
        tenant=tenant,
        document="12345678909",
        defaults={
            "document_type": Customer.DocumentType.CPF,
            "name": "Cliente ALE",
            "address": {
                "logradouro": "Av Cliente",
                "numero": "1",
                "uf": "SP",
                "codigo_ibge": "3504107",
            },
        },
    )
    print(
        f"ALE OK tenant={tenant.slug} "
        f"provider={'new' if created_p else 'exists'} "
        f"customer={'new' if created_c else 'exists'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
