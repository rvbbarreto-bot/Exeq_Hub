# Generated manually for U5-CCE xml_cce artifact kind

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nfe", "0002_nfe_artifact_i1"),
    ]

    operations = [
        migrations.AlterField(
            model_name="nfeartifact",
            name="kind",
            field=models.CharField(
                choices=[
                    ("xml_authorized", "XML autorizado"),
                    ("xml_cancel", "XML cancelamento"),
                    ("xml_cce", "XML CCe (última)"),
                    ("danfe_pdf", "DANFE PDF"),
                ],
                max_length=32,
                verbose_name="Tipo",
            ),
        ),
    ]
