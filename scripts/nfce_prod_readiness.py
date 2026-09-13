"""Checklist pré-emissão NFC-e produção — tenant/emitente ALE ou CNPJ informado.

Uso:
  python scripts/nfce_prod_readiness.py
  python scripts/nfce_prod_readiness.py --cnpj 61536366000174 --tenant ALE
"""

from __future__ import annotations

import argparse
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
from apps.master_data.models import Provider
from apps.nfce.gate import build_gate_payload
from apps.nfce.user_messages import format_nfce_gate_errors


def main() -> int:
    parser = argparse.ArgumentParser(description="NFC-e produção — readiness gate")
    parser.add_argument("--tenant", default="ALE", help="slug do tenant")
    parser.add_argument("--cnpj", default="", help="CNPJ emitente (opcional)")
    args = parser.parse_args()

    tenant = Tenant.objects.filter(slug=args.tenant).first()
    if tenant is None:
        print(f"FAIL tenant '{args.tenant}' não encontrado")
        return 1

    providers = Provider.objects.filter(tenant=tenant, is_active=True)
    if args.cnpj:
        cnpj = "".join(ch for ch in args.cnpj if ch.isdigit())
        providers = providers.filter(document=cnpj)
    provider = providers.first()
    if provider is None:
        print("FAIL nenhum emitente ativo para o filtro")
        return 1

    ie = (provider.state_registration or "").strip()
    print(f"Tenant: {tenant.slug}")
    print(f"Emitente: {provider.legal_name} CNPJ {provider.document}")
    print(f"IE cadastro: {ie or '(vazio)'}")

    payload = build_gate_payload(
        tenant=tenant,
        provider_id=str(provider.id),
        tp_amb="1",
    )
    failed = [c for c in payload.get("checks") or [] if c.get("must") and not c.get("ok")]
    if payload.get("can_create"):
        print("OK gate NFC-e produção — pode emitir no PDV")
        return 0

    print("FAIL gate NFC-e produção:")
    print(format_nfce_gate_errors(failed))
    for c in failed:
        print(f"  - [{c.get('id')}] {c.get('label')}")
    if ie.upper() in {"ISENTO", "ISENTA"}:
        print(
            "\nAção: Hub → Cadastros → Empresas → desmarcar Isento de IE → "
            "informar IE numérica da SEFAZ → salvar → nova emissão."
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
