from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.master_data.nbs_import import NbsImportError, import_nbs_xlsx


class Command(BaseCommand):
    help = (
        "Importa Lista NBS (Anexo B NFS-e — aba LISTA.NBS*) como versão publicada "
        "do catálogo global NBS."
    )

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", type=str, help="Caminho do arquivo .xlsx")
        parser.add_argument(
            "--label",
            required=True,
            help="Rótulo único da versão (ex.: NBS_v2.0-2026-01)",
        )
        parser.add_argument(
            "--sheet",
            default="",
            help="Nome da aba (default: auto-detect LISTA.NBS*)",
        )
        parser.add_argument(
            "--no-publish",
            action="store_true",
            help="Importa como rascunho (não publica)",
        )
        parser.add_argument("--notes", default="", help="Observações")

    def handle(self, *args, **options):
        path = Path(options["xlsx_path"])
        sheet = (options["sheet"] or "").strip() or None
        try:
            version = import_nbs_xlsx(
                path=path,
                version_label=options["label"],
                publish=not options["no_publish"],
                sheet_name=sheet,
                notes=options["notes"] or "",
            )
        except NbsImportError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"OK NBS {version.version_label}: {version.row_count} códigos "
                f"(aba={version.sheet_name}, status={version.status})"
            )
        )
