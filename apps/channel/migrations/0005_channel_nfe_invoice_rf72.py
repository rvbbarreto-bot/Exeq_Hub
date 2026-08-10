from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("channel", "0004_channelnotification_provider"),
        ("nfe", "0002_nfe_artifact_i1"),
    ]

    operations = [
        migrations.AddField(
            model_name="channelsession",
            name="nfe_invoice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="channel_sessions",
                to="nfe.nfeinvoice",
                verbose_name="Emissão NF-e",
            ),
        ),
        migrations.AddField(
            model_name="channelnotification",
            name="nfe_invoice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="channel_notifications",
                to="nfe.nfeinvoice",
                verbose_name="NF-e",
            ),
        ),
    ]
