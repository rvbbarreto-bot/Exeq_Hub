from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nfe", "0006_product_st_ipi"),
    ]

    operations = [
        migrations.AddField(
            model_name="nfeproduct",
            name="gtin",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Opcional. Vazio → SEM GTIN no XML.",
                max_length=14,
                verbose_name="GTIN/EAN",
            ),
        ),
    ]
