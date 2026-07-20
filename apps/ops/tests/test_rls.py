import pytest
from django.db import connection

from apps.master_data.models import Provider, TaxRegime
from apps.master_data.services import create_provider
from shared.rls import set_rls


@pytest.mark.django_db
def test_rls_isolates_tenant_rows(tenant_a, tenant_b):
    if connection.vendor != "postgresql":
        pytest.skip("RLS only on PostgreSQL")

    create_provider(
        tenant=tenant_a,
        document="00000000000191",
        legal_name="A",
        tax_regime=TaxRegime.SIMPLES,
    )
    create_provider(
        tenant=tenant_b,
        document="00000000000272",
        legal_name="B",
        tax_regime=TaxRegime.SIMPLES,
    )

    set_rls(tenant_id=str(tenant_a.id), bypass=False)
    try:
        names = list(Provider.objects.values_list("legal_name", flat=True))
        assert names == ["A"]
    finally:
        set_rls(bypass=True)

    set_rls(tenant_id=str(tenant_b.id), bypass=False)
    try:
        names = list(Provider.objects.values_list("legal_name", flat=True))
        assert names == ["B"]
    finally:
        set_rls(bypass=True)


@pytest.mark.django_db
def test_rls_policy_installed():
    if connection.vendor != "postgresql":
        pytest.skip("RLS only on PostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM pg_policies
            WHERE tablename = 'master_data_provider'
              AND policyname = 'tenant_isolation'
            """
        )
        assert cursor.fetchone() is not None
