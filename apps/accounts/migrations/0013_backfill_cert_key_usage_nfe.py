"""Backfill key_usage legado — incluir 'nfe' em certificados das/nfse only."""

from django.db import migrations


def forwards(apps, schema_editor):
    DigitalCertificate = apps.get_model("accounts", "DigitalCertificate")
    legacy = frozenset({"das", "nfse"})
    for cert in DigitalCertificate.objects.exclude(status="revoked").iterator():
        usages = list(cert.key_usage or [])
        if not usages or "nfe" in usages:
            continue
        if set(usages) <= legacy:
            cert.key_usage = list(dict.fromkeys([*usages, "nfe"]))
            cert.save(update_fields=["key_usage", "updated_at"])


def backwards(apps, schema_editor):
    DigitalCertificate = apps.get_model("accounts", "DigitalCertificate")
    for cert in DigitalCertificate.objects.iterator():
        usages = list(cert.key_usage or [])
        if "nfe" in usages and set(usages) <= {"das", "nfse", "nfe"}:
            cert.key_usage = [u for u in usages if u != "nfe"]
            cert.save(update_fields=["key_usage", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_product_st_ipi"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
