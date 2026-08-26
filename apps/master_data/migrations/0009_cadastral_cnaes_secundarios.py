from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0008_servicecatalogitem_operation_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="cnaes_secundarios",
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name="CNAEs secundários",
            ),
        ),
        migrations.AddField(
            model_name="provider",
            name="cnaes_secundarios",
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name="CNAEs secundários",
            ),
        ),
    ]
