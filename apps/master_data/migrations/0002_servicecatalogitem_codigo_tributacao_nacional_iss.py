from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicecatalogitem",
            name="codigo_tributacao_nacional_iss",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
    ]
