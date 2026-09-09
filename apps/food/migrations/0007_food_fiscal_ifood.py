# Generated manually — iFood fiscal slice (Opção B)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_plan_subscription"),
        ("food", "0006_food_payment_foundation"),
        ("nfce", "0002_nfce_artifacts"),
        ("nfe", "0005_nfe_transmission_attempt"),
    ]

    operations = [
        migrations.AddField(
            model_name="foodproduct",
            name="nfe_product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="food_products",
                to="nfe.nfeproduct",
                verbose_name="Produto fiscal (NFC-e)",
            ),
        ),
        migrations.AddField(
            model_name="foodorder",
            name="fiscal_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("pending", "Pendente emissão"),
                    ("processing", "Processando"),
                    ("authorized", "Autorizada"),
                    ("rejected", "Rejeitada"),
                    ("failed", "Falhou"),
                    ("ignored", "Ignorado"),
                    ("cancelled", "Cancelada"),
                ],
                default="",
                max_length=16,
                verbose_name="Status fiscal",
            ),
        ),
        migrations.AddField(
            model_name="foodorder",
            name="fiscal_warnings",
            field=models.JSONField(blank=True, default=list, verbose_name="Avisos fiscais"),
        ),
        migrations.AddField(
            model_name="foodorder",
            name="fiscal_rejection_code",
            field=models.CharField(
                blank=True,
                default="",
                max_length=32,
                verbose_name="Código rejeição fiscal",
            ),
        ),
        migrations.AddField(
            model_name="foodorder",
            name="fiscal_rejection_message",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Mensagem rejeição fiscal",
            ),
        ),
        migrations.AddField(
            model_name="foodorder",
            name="fiscal_emit_attempt",
            field=models.PositiveIntegerField(
                default=0,
                verbose_name="Tentativas emissão fiscal",
            ),
        ),
        migrations.AddField(
            model_name="foodorder",
            name="fiscal_ignored_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Ignorado em"),
        ),
        migrations.AddField(
            model_name="foodorder",
            name="fiscal_ignored_reason",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Motivo ignorado",
            ),
        ),
        migrations.AddField(
            model_name="foodorder",
            name="nfce_invoice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="food_orders",
                to="nfce.nfceinvoice",
                verbose_name="NFC-e vinculada",
            ),
        ),
        migrations.AddIndex(
            model_name="foodorder",
            index=models.Index(
                fields=["tenant", "channel", "fiscal_status"],
                name="idx_food_order_fiscal",
            ),
        ),
    ]
