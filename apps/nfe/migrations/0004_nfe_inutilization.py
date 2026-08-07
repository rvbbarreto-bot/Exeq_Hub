# Generated manually for U15 NfeInutilization

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_electronic_proxy"),
        ("master_data", "0007_nfe_greenfield_u2"),
        ("nfe", "0003_nfe_artifact_xml_cce"),
    ]

    operations = [
        migrations.CreateModel(
            name="NfeInutilization",
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
                ("series", models.PositiveIntegerField(verbose_name="Série")),
                ("tp_amb", models.CharField(max_length=1, verbose_name="Ambiente")),
                ("ano", models.CharField(max_length=2, verbose_name="Ano (AA)")),
                ("n_ini", models.PositiveIntegerField(verbose_name="nNF inicial")),
                ("n_fin", models.PositiveIntegerField(verbose_name="nNF final")),
                ("x_just", models.CharField(max_length=255, verbose_name="Justificativa")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("accepted", "Homologada"),
                            ("rejected", "Rejeitada"),
                            ("failed", "Falhou"),
                        ],
                        max_length=16,
                        verbose_name="Status",
                    ),
                ),
                (
                    "protocol",
                    models.CharField(
                        blank=True, default="", max_length=60, verbose_name="Protocolo"
                    ),
                ),
                (
                    "provider_raw",
                    models.JSONField(blank=True, default=dict, verbose_name="Raw SEFAZ"),
                ),
                (
                    "actor",
                    models.CharField(
                        blank=True, default="", max_length=120, verbose_name="Ator"
                    ),
                ),
                (
                    "provider",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="nfe_inutilizations",
                        to="master_data.provider",
                        verbose_name="Emitente",
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
                "verbose_name": "Inutilização NF-e",
                "verbose_name_plural": "Inutilizações NF-e",
            },
        ),
        migrations.AddIndex(
            model_name="nfeinutilization",
            index=models.Index(
                fields=["tenant", "provider", "series", "tp_amb"],
                name="nfe_nfeinu_tenant__6a5b1e_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="nfeinutilization",
            index=models.Index(
                fields=["tenant", "created_at"], name="nfe_nfeinu_tenant__f7c2a0_idx"
            ),
        ),
    ]
