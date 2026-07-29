from django.db import migrations, models


def _backfill_idempotency(apps, schema_editor):
    Appointment = apps.get_model("scheduling", "Appointment")
    for appt in Appointment.objects.filter(idempotency_key=""):
        appt.idempotency_key = f"mig-{appt.pk}"
        appt.save(update_fields=["idempotency_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("scheduling", "0001_initial_exeq_agendador"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="idempotency_key",
            field=models.CharField(
                default="",
                max_length=128,
                verbose_name="Chave de idempotência",
            ),
            preserve_default=False,
        ),
        migrations.RunPython(_backfill_idempotency, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="appointment",
            constraint=models.UniqueConstraint(
                fields=("tenant", "idempotency_key"),
                name="uq_scheduling_appointment_idempotency",
            ),
        ),
    ]
