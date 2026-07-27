from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal.exceptions import NationalCatalogError, RtcClassificationError
from apps.fiscal.rtc_assessment import compute_ibscbs_base, formula_period_for
from apps.fiscal.rtc_catalog_guard import assert_national_service_code
from apps.fiscal.rtc_classification import (
    resolve_rtc_classification,
    seed_minimal_rtc_pack,
)
from apps.fiscal.rtc_emission import build_rtc_emission_context, focus_rtc_field_map
from apps.fiscal.rtc_forensic import build_forensic_snapshot
from apps.master_data.models import ServiceCatalogItem
from apps.master_data.national_service_import import import_national_service_xlsx
from apps.master_data.tests.test_national_service_import import _write_sample_xlsx


def test_formula_period_boundaries():
    assert formula_period_for(date(2026, 12, 31)) == "2026_test"
    assert formula_period_for(date(2027, 1, 1)) == "2027_2032_transition"
    assert formula_period_for(date(2033, 1, 1)) == "2033_full"


def test_compute_ibscbs_base_2026_deducts_pis_cofins():
    out = compute_ibscbs_base(
        amount_cents=10_000,
        iss_rate=Decimal("0.02"),
        pis_rate=Decimal("0.0065"),
        cofins_rate=Decimal("0.03"),
        competence_date=date(2026, 8, 3),
    )
    assert out["formula_period"] == "2026_test"
    # 100 - 2 ISS - 0.65 PIS - 3 COFINS = 94.35
    assert out["v_bc"] == "94.35"
    assert out["p_cbs"] == "0.0090"
    assert out["p_ibs"] == "0.0010"
    assert Decimal(out["v_cbs"]) == Decimal("0.85")
    assert Decimal(out["v_ibs"]) == Decimal("0.09")


def test_compute_ibscbs_base_2027_skips_pis_cofins():
    out = compute_ibscbs_base(
        amount_cents=10_000,
        iss_rate=Decimal("0.02"),
        pis_rate=Decimal("0.0065"),
        cofins_rate=Decimal("0.03"),
        competence_date=date(2027, 6, 1),
    )
    assert out["formula_period"] == "2027_2032_transition"
    # 100 - 2 ISS = 98.00
    assert out["v_bc"] == "98.00"


@pytest.mark.django_db
def test_national_catalog_enforced_when_published(tmp_path, tenant_a, settings):
    settings.RTC_ENFORCE_NATIONAL_CATALOG = True
    xlsx = tmp_path / "anexo.xlsx"
    _write_sample_xlsx(xlsx)
    import_national_service_xlsx(path=xlsx, version_label="rtc-guard", publish=True)

    bad = ServiceCatalogItem(
        tenant=tenant_a,
        service_code="x",
        description="x",
        codigo_tributacao_nacional_iss="99999",
    )
    with pytest.raises(NationalCatalogError):
        assert_national_service_code(service=bad)

    ok = ServiceCatalogItem(
        tenant=tenant_a,
        service_code="10101",
        description="ok",
        codigo_tributacao_nacional_iss="10101",
    )
    result = assert_national_service_code(service=ok)
    assert result["status"] == "ok"


@pytest.mark.django_db
def test_rtc_classification_seed_and_resolve():
    seed_minimal_rtc_pack()
    resolved = resolve_rtc_classification()
    assert resolved["status"] == "ok"
    assert resolved["cst"] == "000"
    assert resolved["c_class_trib"] == "000001"

    with pytest.raises(RtcClassificationError):
        resolve_rtc_classification(cst="999")


@pytest.mark.django_db
def test_build_rtc_context_shadow(tenant_a, settings):
    settings.RTC_NFSEN_MODE = "shadow"
    settings.RTC_ENFORCE_NATIONAL_CATALOG = False
    seed_minimal_rtc_pack()

    class Rule:
        iss_rate = Decimal("0.02")
        pis_rate = Decimal("0")
        cofins_rate = Decimal("0")

    service = ServiceCatalogItem(
        tenant=tenant_a,
        service_code="1.01",
        description="Serviço",
        codigo_tributacao_nacional_iss="",
    )
    ctx = build_rtc_emission_context(
        service=service,
        rule=Rule(),
        amount_cents=10_000,
        competence_date=date(2026, 8, 3),
        iss_payload={"iss_rate": "0.0200"},
        layout="nfsen",
    )
    assert ctx["mode"] == "shadow"
    assert ctx["focus_rtc_fields"] == {}
    assert ctx["params"]["forensic"]["schema"] == "exeq.fiscal.forensic.v1"
    assert ctx["params"]["rtc"]["assessment"]["v_bc"] == "98.00"
    fields = focus_rtc_field_map(ctx["params"]["rtc"])
    assert fields["situacao_tributaria_ibscbs"] == "000"


def test_forensic_hash_stable():
    a = build_forensic_snapshot(
        iss_payload={"iss_rate": "0.02"},
        rtc_block={"status": "computed"},
        national_catalog={"status": "skipped"},
        layout="nfsen",
    )
    b = build_forensic_snapshot(
        iss_payload={"iss_rate": "0.02"},
        rtc_block={"status": "computed"},
        national_catalog={"status": "skipped"},
        layout="nfsen",
    )
    assert a["forensic_sha256"] == b["forensic_sha256"]
