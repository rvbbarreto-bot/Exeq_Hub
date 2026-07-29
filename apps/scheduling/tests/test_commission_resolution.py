from apps.scheduling.commission_resolution import (
    CommissionRuleView,
    compute_commission_cents,
    resolve_best_commission_rule,
)


def test_resolve_prefers_more_specific_rule():
    general = CommissionRuleView(
        id="1",
        branch_id=None,
        professional_id=None,
        service_id=None,
        rule_kind="percent",
        percent_basis_points=3000,
        fixed_cents=None,
        priority=0,
    )
    specific = CommissionRuleView(
        id="2",
        branch_id=None,
        professional_id="pro-1",
        service_id="svc-1",
        rule_kind="percent",
        percent_basis_points=5000,
        fixed_cents=None,
        priority=0,
    )
    best = resolve_best_commission_rule(
        branch_id=None,
        professional_id="pro-1",
        service_id="svc-1",
        rules=[general, specific],
    )
    assert best is not None
    assert best.id == "2"
    assert compute_commission_cents(base_amount_cents=10000, rule=best) == 5000


def test_fixed_cents_capped_by_base():
    rule = CommissionRuleView(
        id="3",
        branch_id=None,
        professional_id=None,
        service_id=None,
        rule_kind="fixed_cents",
        percent_basis_points=None,
        fixed_cents=9000,
        priority=1,
    )
    assert compute_commission_cents(base_amount_cents=5000, rule=rule) == 5000
