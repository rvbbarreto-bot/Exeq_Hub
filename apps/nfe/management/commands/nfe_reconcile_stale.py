"""Ops: reengata NF-e em polling/submitting/cancel órfãos (RF-46)."""

from django.core.management.base import BaseCommand

from apps.nfe.reconciliation import reconcile_stale_nfe_batch


class Command(BaseCommand):
    help = "Reconcilia NF-e em estados intermediários stale (polling/submitting/cancel_requested)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        stats = reconcile_stale_nfe_batch(limit=int(options["limit"] or 50))
        self.stdout.write(self.style.SUCCESS(str(stats)))
