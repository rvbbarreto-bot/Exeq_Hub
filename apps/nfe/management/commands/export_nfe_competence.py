"""Export manifest NF-e autorizadas por competência (ACC-01)."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from apps.accounts.models import Tenant
from apps.nfe.competence_export import export_competence_package


class Command(BaseCommand):
    help = "Exporta manifest JSON NF-e autorizadas/canceladas por competência (issue_date)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Slug do tenant")
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument(
            "--out",
            default=".storage/nfe_exports",
            help="Diretório de saída",
        )

    def handle(self, *args, **options):
        tenant = Tenant.objects.get(slug=options["tenant"])
        result = export_competence_package(
            tenant_id=tenant.id,
            year=options["year"],
            month=options["month"],
            out_dir=Path(options["out"]),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Export {result['competence']}: {result['count']} notas → {result['path']}"
            )
        )
