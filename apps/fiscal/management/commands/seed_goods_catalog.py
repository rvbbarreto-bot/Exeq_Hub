"""Publica catálogo mercadorias MVP (NCM/CFOP/unidade)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.fiscal.goods_catalog import seed_and_publish


class Command(BaseCommand):
    help = "Seed e publica catálogo mercadorias goods-v1.0 (NCM/CFOP/unidade)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--label",
            default="goods-v1.0",
            help="Rótulo da versão (default: goods-v1.0)",
        )

    def handle(self, *args, **options):
        version = seed_and_publish(version_label=options["label"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Catálogo {version.version_label} publicado — {version.row_count} itens"
            )
        )
