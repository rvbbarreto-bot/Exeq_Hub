from django.core.management.base import BaseCommand

from apps.fiscal.rtc_classification import seed_minimal_rtc_pack


class Command(BaseCommand):
    help = "Publica seed mínimo RTC (CST/cClassTrib/cIndOp) para shadow/homologação."

    def handle(self, *args, **options):
        version = seed_minimal_rtc_pack()
        self.stdout.write(
            self.style.SUCCESS(
                f"RTC seed OK: {version.version_label} status={version.status} "
                f"codes={version.codes.count()}"
            )
        )
