from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("master_data", "0007_nfe_greenfield_u2"),
    ]

    operations = [
        migrations.AddField(
            model_name="servicecatalogitem",
            name="operation_kind",
            field=models.CharField(
                choices=[
                    ("servico_iss", "Serviço tributável ISS"),
                    ("locacao_bem", "Locação de bem (sem NFS-e)"),
                ],
                default="servico_iss",
                max_length=32,
                verbose_name="Tipo de operação",
            ),
        ),
    ]
