from django.db import migrations

TENANT_TABLES = [
    "accounts_tenantmembership",
    "accounts_tenantsecret",
    "accounts_digitalcertificate",
    "accounts_certificateaudit",
    "master_data_provider",
    "master_data_customer",
    "master_data_servicecatalogitem",
    "fiscal_fiscalprofile",
    "fiscal_taxrulecatalog",
    "fiscal_municipaltaxrule",
    "ops_outboxmessage",
    "ops_storedfile",
    "issuance_nfissue",
    "issuance_fiscalrulesnapshot",
    "issuance_nfissueevent",
    "billing_charge",
    "billing_webhookinbox",
    "billing_paymentevent",
    "das_guiafiscal",
    "channel_channelsession",
    "channel_channelnotification",
]


def _enable_rls(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in TENANT_TABLES:
            cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cursor.execute(
                f"""
                CREATE POLICY tenant_isolation ON "{table}"
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
        for table in TENANT_TABLES:
            cursor.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
            cursor.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
            cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


class Migration(migrations.Migration):
    dependencies = [
        ("channel", "0001_initial"),
        ("ops", "0002_storedfile"),
        ("accounts", "0004_digitalcertificate_stored_file_and_more"),
        ("das", "0001_initial"),
        ("billing", "0001_initial"),
        ("issuance", "0001_initial"),
        ("fiscal", "0001_initial"),
        ("master_data", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(_enable_rls, _disable_rls),
    ]
