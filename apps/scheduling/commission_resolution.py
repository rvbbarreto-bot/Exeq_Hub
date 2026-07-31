"""Resolução de regra de comissão (port barbearia-saas rule-resolution)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommissionRuleView:
    id: object
    branch_id: object | None
    professional_id: object | None
    service_id: object | None
    rule_kind: str
    percent_basis_points: int | None
    fixed_cents: int | None
    priority: int


def _specificity(rule: CommissionRuleView) -> int:
    return (
        (100 if rule.branch_id else 0)
        + (10 if rule.professional_id else 0)
        + (1 if rule.service_id else 0)
    )


def rule_matches(
    *,
    branch_id,
    professional_id,
    service_id,
    rule: CommissionRuleView,
) -> bool:
    if rule.branch_id is not None and (
        branch_id is None or str(rule.branch_id) != str(branch_id)
    ):
        return False
    if rule.professional_id is not None and str(rule.professional_id) != str(
        professional_id
    ):
        return False
    if rule.service_id is not None and (
        service_id is None or str(rule.service_id) != str(service_id)
    ):
        return False
    return True


def resolve_best_commission_rule(
    *,
    branch_id,
    professional_id,
    service_id,
    rules: list[CommissionRuleView],
) -> CommissionRuleView | None:
    matches = [
        r
        for r in rules
        if rule_matches(
            branch_id=branch_id,
            professional_id=professional_id,
            service_id=service_id,
            rule=r,
        )
    ]
    if not matches:
        return None
    matches.sort(
        key=lambda r: (_specificity(r), r.priority, str(r.id)),
        reverse=True,
    )
    return matches[0]


def compute_commission_cents(*, base_amount_cents: int, rule: CommissionRuleView) -> int:
    base = max(0, int(base_amount_cents))
    if rule.rule_kind == "percent":
        bp = int(rule.percent_basis_points or 0)
        return min(base, round((base * bp) / 10000))
    return min(base, int(rule.fixed_cents or 0))
