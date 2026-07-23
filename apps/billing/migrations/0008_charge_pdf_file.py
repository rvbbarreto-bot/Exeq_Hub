# Generated manually for Charge.pdf_file → StoredFile (boleto_pdf).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0007_charge_emission_fields"),
        ("ops", "0006_field_verbose_names_pt"),
    ]

    operations = [
        migrations.AddField(
            model_name="charge",
            name="pdf_file",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="charges",
                to="ops.storedfile",
                verbose_name="PDF do boleto",
            ),
        ),
    ]
