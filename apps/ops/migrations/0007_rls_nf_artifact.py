"""RLS em issuance_nfartifact (SEC-P1-04 / EX-SEC-01)."""

from django.db import migrations

TABLE = "issuance_nfartifact"


def _enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY')
        cursor.execute(f'ALTER TABLE "{TABLE}" FORCE ROW LEVEL SECURITY')
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{TABLE}"')
        cursor.execute(
            f"""
            CREATE POLICY tenant_isolation ON "{TABLE}"
              USING (
                current_setting('app.bypass_rls', true) = 'on'
                OR tenant_id::text = current_setting('app.tenant_id', true)
              )
              WITH CHECK (
                current_setting('app.bypass_rls', true) = 'on'
                OR tenant_id::text = current_setting('app.tenant_id', true)
              )
            """
        )


def _disable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{TABLE}"')
        cursor.execute(f'ALTER TABLE "{TABLE}" NO FORCE ROW LEVEL SECURITY')
        cursor.execute(f'ALTER TABLE "{TABLE}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [
        ("ops", "0006_field_verbose_names_pt"),
        ("issuance", "0002_nf_artifact"),
    ]

    operations = [
        migrations.RunPython(_enable_rls, _disable_rls),
    ]
