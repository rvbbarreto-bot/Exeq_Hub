from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.master_data.national_service_import import (
    NationalServiceImportError,
    import_national_service_xlsx,
)


class Command(BaseCommand):
    help = (
        "Importa Anexo B (XLSX) — aba LISTA.SERV.NAC. — como versão da "
        "Lista de Serviço Nacional."
    )

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", type=str, help="Caminho do arquivo .xlsx")
        parser.add_argument(
            "--label",
            required=True,
            help="Rótulo único da versão (ex.: 2026-01-22)",
        )
        parser.add_argument(
            "--no-publish",
            action="store_true",
            help="Importa como rascunho (não publica)",
        )
        parser.add_argument("--notes", default="", help="Observações")

    def handle(self, *args, **options):
        path = Path(options["xlsx_path"])
        try:
            version = import_national_service_xlsx(
                path=path,
                version_label=options["label"],
                publish=not options["no_publish"],
                notes=options["notes"] or "",
            )
        except NationalServiceImportError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"OK {version.version_label}: {version.row_count} códigos "
                f"(status={version.status})"
            )
        )
