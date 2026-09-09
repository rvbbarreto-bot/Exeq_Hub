"""Gate Fase 2 — integração real iFood + cert + CSC (somente leitura)."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import DigitalCertificate, Tenant
from apps.food.models import FoodMarketplaceConnection, FoodProduct
from apps.master_data.models import Provider


def run_phase2_readiness(*, tenant: Tenant) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(cid: str, ok: bool, detail: str, *, blocker: bool = True) -> None:
        checks.append({"id": cid, "ok": ok, "detail": detail, "blocker": blocker})

    provider = Provider.objects.filter(tenant=tenant, is_active=True).order_by("created_at").first()
    doc = (provider.document if provider else "") or tenant.document
    addr = provider.address if provider and isinstance(provider.address, dict) else {}
    uf = str(addr.get("uf") or "").upper()
    ibge = str(addr.get("codigo_ibge") or "").strip()

    now = timezone.now()
    cert = (
        DigitalCertificate.objects.filter(
            tenant=tenant,
            cnpj=doc,
            status__in=[
                DigitalCertificate.Status.ACTIVE,
                DigitalCertificate.Status.EXPIRING,
            ],
            not_after__gt=now,
        )
        .order_by("-is_primary", "-not_after")
        .first()
    )
    add(
        "P2-01-CERT-A1",
        cert is not None,
        f"Certificado A1 ativo CNPJ {doc}: {cert.label if cert else 'nenhum'}",
    )

    csc = (getattr(settings, "NFCE_CSC_TOKEN", "") or "").strip()
    csc_id = (getattr(settings, "NFCE_CSC_ID", "") or "").strip()
    add(
        "P2-02-CSC",
        bool(csc) and bool(csc_id),
        f"NFCE_CSC_ID/CSC_TOKEN configurados (id={'ok' if csc_id else 'vazio'})",
    )

    nfce_mode = (getattr(settings, "NFCE_HTTP_MODE", "stub") or "stub").lower()
    add(
        "P2-03-NFCE-HTTP",
        nfce_mode == "http",
        f"NFCE_HTTP_MODE={nfce_mode} (http para SEFAZ/parceiro real)",
    )

    mp_mode = (getattr(settings, "MARKETPLACE_HTTP_MODE", "stub") or "stub").lower()
    add(
        "P2-04-IFOOD-HTTP",
        mp_mode == "http",
        f"MARKETPLACE_HTTP_MODE={mp_mode}",
    )

    conn = FoodMarketplaceConnection.objects.filter(
        tenant=tenant,
        provider=FoodMarketplaceConnection.Provider.IFOOD,
        is_active=True,
    ).first()
    token_ok = bool((getattr(settings, "IFOOD_API_TOKEN", "") or "").strip()) or bool(
        conn and (conn.settings or {}).get("access_token")
    )
    base_ok = bool((getattr(settings, "IFOOD_API_BASE_URL", "") or "").strip())
    add(
        "P2-05-IFOOD-CRED",
        token_ok and base_ok,
        f"iFood token={'ok' if token_ok else 'ausente'} base_url={'ok' if base_ok else 'ausente'}",
    )

    stub_conn = bool(conn and (conn.settings or {}).get("stub_orders"))
    merchant = (conn.merchant_ref if conn else "") or ""
    add(
        "P2-06-MERCHANT-REAL",
        conn is not None and not stub_conn and bool(merchant),
        f"Conexao iFood merchant_ref={merchant or '—'} stub_orders={stub_conn}",
    )

    active = FoodProduct.objects.filter(tenant=tenant, is_active=True).count()
    mapped = FoodProduct.objects.filter(
        tenant=tenant, is_active=True, nfe_product__isnull=False
    ).count()
    add(
        "P2-07-DE-PARA",
        active > 0 and mapped == active,
        f"De-para {mapped}/{active} produtos ativos (100% antes do piloto real)",
        blocker=True,
    )

    add(
        "P2-08-EMITENTE-COMPLETO",
        provider is not None and uf == "SP" and len(ibge) == 7,
        f"Provider SP IBGE7: {provider.legal_name if provider else '—'} uf={uf or '—'} ibge={ibge or '—'}",
    )

    tp_amb = str(getattr(settings, "NFCE_DEFAULT_TP_AMB", "2") or "2")
    add(
        "P2-09-TP-AMB",
        tp_amb in {"1", "2"},
        f"NFCE_DEFAULT_TP_AMB={tp_amb} (2=homolog, 1=prod — alinhar com PO)",
        blocker=False,
    )

    add(
        "P2-10-HOST-PROD",
        not bool(getattr(settings, "DEBUG", False)),
        f"DEBUG={getattr(settings, 'DEBUG', False)}",
    )

    blockers = [c for c in checks if c["blocker"] and not c["ok"]]
    return {
        "tenant_slug": tenant.slug,
        "tenant_id": str(tenant.id),
        "generated_at": timezone.now().isoformat(),
        "phase": "Fase 2 — integração real",
        "ready_for_phase2": len(blockers) == 0,
        "summary": {
            "pass": sum(1 for c in checks if c["ok"]),
            "fail": sum(1 for c in checks if not c["ok"]),
            "blockers": len(blockers),
            "total": len(checks),
        },
        "checks": checks,
        "ops_manual": [
            "Celery worker + beat no host piloto (nao verificavel via ORM).",
            "Upload certificado A1 no Hub/API vinculado ao CNPJ 61536366000174.",
            "Cadastrar CSC NFC-e SP (ID + token) no .env ou vault.",
            "Configurar credenciais iFood Merchant API na conexao marketplace.",
            "Mapear 100% SKUs do cardapio iFood em Hub -> Produtos.",
            "Homolog: NFCE_DEFAULT_TP_AMB=2 + smoke 1 pedido real antes de tpAmb=1.",
        ],
    }
