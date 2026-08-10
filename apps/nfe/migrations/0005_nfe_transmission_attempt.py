# Generated for U20 NfeTransmissionAttempt (RF-44)

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_electronic_proxy"),
        ("nfe", "0004_nfe_inutilization"),
    ]

    operations = [
        migrations.CreateModel(
            name="NfeTransmissionAttempt",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "stage",
                    models.CharField(
                        choices=[
                            ("emit", "Autorização"),
                            ("poll", "Consulta / poll"),
                            ("cancel", "Cancelamento"),
                            ("cce", "CCe"),
                            ("inut", "Inutilização"),
                        ],
                        max_length=16,
                        verbose_name="Etapa",
                    ),
                ),
                (
                    "provider_kind",
                    models.CharField(
                        blank=True, default="", max_length=16, verbose_name="Provider"
                    ),
                ),
                (
                    "result_status",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=32,
                        verbose_name="Status resultado",
                    ),
                ),
                (
                    "http_status",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="HTTP"
                    ),
                ),
                (
                    "c_stat",
                    models.CharField(
                        blank=True, default="", max_length=8, verbose_name="cStat"
                    ),
                ),
                (
                    "x_motivo",
                    models.CharField(
                        blank=True, default="", max_length=512, verbose_name="xMotivo"
                    ),
                ),
                (
                    "access_key",
                    models.CharField(
                        blank=True, default="", max_length=44, verbose_name="Chave"
                    ),
                ),
                (
                    "duration_ms",
                    models.PositiveIntegerField(
                        blank=True, null=True, verbose_name="Duração ms"
                    ),
                ),
                (
                    "correlation_id",
                    models.UUIDField(
                        blank=True, null=True, verbose_name="Correlação"
                    ),
                ),
                (
                    "raw",
                    models.JSONField(
                        blank=True, default=dict, verbose_name="Raw (sanitizado)"
                    ),
                ),
                (
                    "invoice",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transmission_attempts",
                        to="nfe.nfeinvoice",
                        verbose_name="NF-e",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="nfe_nfetransmissionattempt_set",
                        to="accounts.tenant",
                        verbose_name="Tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tentativa SEFAZ NF-e",
                "verbose_name_plural": "Tentativas SEFAZ NF-e",
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="nfetransmissionattempt",
            index=models.Index(
                fields=["tenant", "invoice", "-created_at"],
                name="nfe_nfetran_tenant__7c3e21_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="nfetransmissionattempt",
            index=models.Index(
                fields=["tenant", "stage", "-created_at"],
                name="nfe_nfetran_tenant__a9b4f0_idx",
            ),
        ),
    ]
