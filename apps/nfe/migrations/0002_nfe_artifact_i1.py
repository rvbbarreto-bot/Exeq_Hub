# Generated manually for U3/I1 NfeArtifact

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_electronic_proxy"),
        ("nfe", "0001_nfe_greenfield_u2"),
        ("ops", "0002_storedfile"),
    ]

    operations = [
        migrations.CreateModel(
            name="NfeArtifact",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Criado em"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="Atualizado em"),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("xml_authorized", "XML autorizado"),
                            ("xml_cancel", "XML cancelamento"),
                            ("danfe_pdf", "DANFE PDF"),
                        ],
                        max_length=32,
                        verbose_name="Tipo",
                    ),
                ),
                (
                    "checksum_sha256",
                    models.CharField(max_length=64, verbose_name="Checksum SHA-256"),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="artifacts",
                        to="nfe.nfeinvoice",
                        verbose_name="NF-e",
                    ),
                ),
                (
                    "stored_file",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="nfe_artifacts",
                        to="ops.storedfile",
                        verbose_name="Arquivo",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(app_label)s_%(class)s_set",
                        to="accounts.tenant",
                        verbose_name="Tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Artefato NF-e",
                "verbose_name_plural": "Artefatos NF-e",
            },
        ),
        migrations.AddConstraint(
            model_name="nfeartifact",
            constraint=models.UniqueConstraint(
                fields=("invoice", "kind"),
                name="uq_nfe_artifact_invoice_kind",
            ),
        ),
    ]
