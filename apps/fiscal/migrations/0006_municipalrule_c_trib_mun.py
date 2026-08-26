from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0005_rtc_normative_classification"),
    ]

    operations = [
        migrations.AddField(
            model_name="municipaltaxrule",
            name="c_trib_mun",
            field=models.CharField(
                blank=True,
                default="",
                max_length=16,
                verbose_name="Código tributação municipal (cTribMun)",
            ),
        ),
    ]
