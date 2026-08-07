from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("channel", "0003_field_verbose_names_pt"),
    ]

    operations = [
        migrations.AddField(
            model_name="channelnotification",
            name="provider",
            field=models.CharField(
                blank=True, default="", max_length=16, verbose_name="Provedor WhatsApp"
            ),
        ),
    ]
