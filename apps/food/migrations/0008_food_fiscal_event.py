# B10 — trilha auditoria fiscal iFood

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_plan_subscription"),
        ("food", "0007_food_fiscal_ifood"),
    ]

    operations = [
        migrations.CreateModel(
            name="FoodFiscalEvent",
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
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Criado em")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Atualizado em")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("emit_start", "Início emissão"),
                            ("emit_skip", "Emissão ignorada"),
                            ("emit_done", "Emissão concluída"),
                            ("ignore", "Ignorado"),
                            ("cancel_nfce", "Cancelamento NFC-e"),
                            ("sync_nfce", "Sync NFC-e"),
                            ("reconcile", "Reconcile"),
                        ],
                        max_length=32,
                        verbose_name="Ação",
                    ),
                ),
                (
                    "actor",
                    models.CharField(default="system", max_length=64, verbose_name="Ator"),
                ),
                (
                    "from_status",
                    models.CharField(blank=True, default="", max_length=16, verbose_name="De"),
                ),
                (
                    "to_status",
                    models.CharField(blank=True, default="", max_length=16, verbose_name="Para"),
                ),
                (
                    "attempt",
                    models.PositiveIntegerField(default=0, verbose_name="Tentativa emissão"),
                ),
                (
                    "metadata",
                    models.JSONField(blank=True, null=True, verbose_name="Metadados"),
                ),
                (
                    "occurred_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Em"),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fiscal_events",
                        to="food.foodorder",
                        verbose_name="Pedido",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="food_fiscal_events",
                        to="accounts.tenant",
                        verbose_name="Tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Evento fiscal Food",
                "verbose_name_plural": "Eventos fiscais Food",
                "ordering": ("occurred_at",),
            },
        ),
        migrations.AddIndex(
            model_name="foodfiscalevent",
            index=models.Index(
                fields=["tenant", "order", "-occurred_at"],
                name="idx_food_fiscal_ev_order",
            ),
        ),
        migrations.AddIndex(
            model_name="foodfiscalevent",
            index=models.Index(
                fields=["tenant", "action", "-occurred_at"],
                name="idx_food_fiscal_ev_action",
            ),
        ),
    ]
