"""Ops: reconcilia NFC-e stale (polling/submitting)."""

from django.core.management.base import BaseCommand

from apps.nfce.reconciliation import reconcile_stale_nfce_batch


class Command(BaseCommand):
    help = "Reconcilia NFC-e em polling/submitting stale."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        stats = reconcile_stale_nfce_batch(limit=int(options["limit"] or 50))
        self.stdout.write(self.style.SUCCESS(str(stats)))
