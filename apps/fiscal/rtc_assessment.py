"""Pilar 1 — apuração IBS/CBS para NFS-e (ano-teste e transição)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

MONEY = Decimal("0.01")
RATE = Decimal("0.0001")


def _q_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _q_rate(value: Decimal) -> Decimal:
    return value.quantize(RATE, rounding=ROUND_HALF_UP)


def formula_period_for(competence_date: date) -> str:
    year = competence_date.year
    if year <= 2026:
        return "2026_test"
    if year <= 2032:
        return "2027_2032_transition"
    return "2033_full"


def _rates_for_period(period: str) -> tuple[Decimal, Decimal, Decimal]:
    """Retorna (p_cbs, p_ibs_uf, p_ibs_mun) como fração."""
    if period == "2026_test":
        cbs = Decimal(str(getattr(settings, "RTC_TEST_CBS_RATE", "0.009")))
        ibs = Decimal(str(getattr(settings, "RTC_TEST_IBS_RATE", "0.001")))
        return _q_rate(cbs), _q_rate(ibs), Decimal("0.0000")
    # 2027–2032: IBS simbólico 0,05% UF + 0,05% Mun (calendário ADCT); CBS referência
    # até haver alíquota de referência do Senado no settings, usa teste CBS como placeholder.
    cbs = Decimal(str(getattr(settings, "RTC_TEST_CBS_RATE", "0.009")))
    return _q_rate(cbs), Decimal("0.0005"), Decimal("0.0005")


def compute_ibscbs_base(
    *,
    amount_cents: int,
    iss_rate: Decimal,
    pis_rate: Decimal,
    cofins_rate: Decimal,
    competence_date: date,
    discount_unconditioned: Decimal = Decimal("0"),
    adjustment_bc: Decimal = Decimal("0"),
) -> dict:
    """
    Base IBS/CBS (síntese NT NFS-e):
    ≤2026: vBC = vServ − desc − ajuste − vISSQN − vPIS − vCOFINS
    2027–2032: vBC = vServ − desc − ajuste − vISSQN
    """
    v_serv = _q_money(Decimal(amount_cents) / Decimal(100))
    period = formula_period_for(competence_date)
    v_iss = _q_money(v_serv * Decimal(iss_rate))
    v_pis = _q_money(v_serv * Decimal(pis_rate))
    v_cofins = _q_money(v_serv * Decimal(cofins_rate))
    desc = _q_money(Decimal(discount_unconditioned))
    adj = _q_money(Decimal(adjustment_bc))

    v_bc = v_serv - desc - adj - v_iss
    if period == "2026_test":
        v_bc = v_bc - v_pis - v_cofins
    if v_bc < 0:
        v_bc = Decimal("0.00")
    v_bc = _q_money(v_bc)

    p_cbs, p_ibs_uf, p_ibs_mun = _rates_for_period(period)
    v_cbs = _q_money(v_bc * p_cbs)
    v_ibs_uf = _q_money(v_bc * p_ibs_uf)
    v_ibs_mun = _q_money(v_bc * p_ibs_mun)
    v_ibs = _q_money(v_ibs_uf + v_ibs_mun)

    return {
        "formula_period": period,
        "v_serv": str(v_serv),
        "v_issqn": str(v_iss),
        "v_pis": str(v_pis),
        "v_cofins": str(v_cofins),
        "v_desc_incond": str(desc),
        "v_ajuste_bc": str(adj),
        "v_bc": str(v_bc),
        "p_cbs": str(p_cbs),
        "p_ibs_uf": str(p_ibs_uf),
        "p_ibs_mun": str(p_ibs_mun),
        "p_ibs": str(_q_rate(p_ibs_uf + p_ibs_mun)),
        "v_cbs": str(v_cbs),
        "v_ibs_uf": str(v_ibs_uf),
        "v_ibs_mun": str(v_ibs_mun),
        "v_ibs": str(v_ibs),
    }
