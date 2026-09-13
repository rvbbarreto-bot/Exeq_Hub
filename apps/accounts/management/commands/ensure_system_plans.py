from django.core.management.base import BaseCommand

from apps.accounts.plan_services import ensure_system_plans


class Command(BaseCommand):
    help = "Garante planos seed (starter, contábil 5/20, enterprise)."

    def handle(self, *args, **options):
        plans = ensure_system_plans()
        for p in plans:
            self.stdout.write(
                f"  {p.code}: {p.name} limits={p.limits}"
            )
        self.stdout.write(self.style.SUCCESS(f"{len(plans)} plano(s) ok."))
