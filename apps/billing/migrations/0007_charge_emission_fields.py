from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0006_payment_provider_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="charge",
            name="charge_kind",
            field=models.CharField(
                choices=[
                    ("simple", "Pagamento único"),
                    ("installment", "Parcelado"),
                    ("recurring", "Recorrente"),
                ],
                default="simple",
                max_length=16,
                verbose_name="Tipo de emissão",
            ),
        ),
        migrations.AddField(
            model_name="charge",
            name="installment_count",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Total de parcelas"
            ),
        ),
        migrations.AddField(
            model_name="charge",
            name="installment_number",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Parcela"
            ),
        ),
        migrations.AddField(
            model_name="charge",
            name="message_lines",
            field=models.JSONField(
                blank=True, default=list, verbose_name="Linhas da descrição (boleto)"
            ),
        ),
        migrations.AddField(
            model_name="charge",
            name="mora_percent_am",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="Juros % a.m.",
            ),
        ),
        migrations.AddField(
            model_name="charge",
            name="multa_percent",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                verbose_name="Multa %",
            ),
        ),
        migrations.AddField(
            model_name="charge",
            name="num_dias_agenda",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Dias após vencimento"
            ),
        ),
        migrations.AddField(
            model_name="charge",
            name="schedule_group_id",
            field=models.UUIDField(
                blank=True, null=True, verbose_name="Grupo da agenda"
            ),
        ),
        migrations.AddField(
            model_name="charge",
            name="seu_numero",
            field=models.CharField(
                blank=True,
                default="",
                max_length=15,
                verbose_name="Código de controle",
            ),
        ),
        migrations.AddIndex(
            model_name="charge",
            index=models.Index(
                fields=["tenant", "schedule_group_id"],
                name="billing_charge_sched_grp_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="charge",
            index=models.Index(
                fields=["tenant", "seu_numero"],
                name="billing_charge_seu_numero_idx",
            ),
        ),
    ]
