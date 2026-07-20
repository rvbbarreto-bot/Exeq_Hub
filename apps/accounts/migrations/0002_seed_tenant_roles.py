from django.db import migrations


def seed_roles(apps, schema_editor):
    TenantRole = apps.get_model("accounts", "TenantRole")
    roles = (
        ("tenant_admin", "Tenant Admin"),
        ("operator", "Operator"),
        ("accountant", "Accountant"),
        ("readonly", "Read Only"),
    )
    for code, name in roles:
        TenantRole.objects.get_or_create(
            code=code,
            defaults={"name": name, "is_system": True, "permissions": []},
        )


def unseed_roles(apps, schema_editor):
    TenantRole = apps.get_model("accounts", "TenantRole")
    TenantRole.objects.filter(
        code__in=["tenant_admin", "operator", "accountant", "readonly"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_roles, unseed_roles),
    ]
