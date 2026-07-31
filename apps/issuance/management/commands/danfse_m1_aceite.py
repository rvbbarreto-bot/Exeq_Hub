"""Pacote de aceite M1 (G-PDF) — PDFs + cobertura checklist para PO/fiscal."""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from integrations.nfse.danfse import LAYOUT_VERSION, evaluate_danfse_checklist, render_danfse_pdf

FIXTURES = Path(settings.BASE_DIR) / "integrations" / "nfse" / "tests" / "fixtures"


class Command(BaseCommand):
    help = "Gera PDFs + nota de cobertura M1 (≥80% NT 008) para aceite PO/fiscal."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out-dir",
            default=".storage/m1_aceite",
            help="Pasta de saída (default .storage/m1_aceite)",
        )

    def handle(self, *args, **options):
        out = Path(options["out_dir"])
        out.mkdir(parents=True, exist_ok=True)
        cases = [
            ("nfse_autorizada_minimal.xml", "danfse_autorizada_lab.pdf", False),
            ("nfse_autorizada_prod_sample.xml", "danfse_autorizada_prod_sample.pdf", False),
            ("nfse_cancelada_minimal.xml", "danfse_cancelada_lab.pdf", True),
        ]
        report = {
            "layout_version": LAYOUT_VERSION,
            "criterion_m1": "checklist >= 80%",
            "fixtures": {},
        }
        for fixture, pdf_name, cancelled in cases:
            xml = (FIXTURES / fixture).read_bytes()
            pdf = render_danfse_pdf(xml, cancelled=cancelled)
            (out / pdf_name).write_bytes(pdf)
            result = evaluate_danfse_checklist(xml, cancelled=cancelled)
            report["fixtures"][fixture] = {
                "pdf": str(out / pdf_name),
                "coverage": round(result.coverage, 4),
                "ok_m1": result.ok_m1,
                "ok_m4": getattr(result, "ok_m4", result.coverage >= 0.95),
                "passed": result.passed,
            }
            self.stdout.write(
                f"{fixture}: coverage={result.coverage:.0%} ok_m1={result.ok_m1} -> {pdf_name}"
            )
        note = out / "cobertura_m1.json"
        note.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        all_ok = all(v["ok_m1"] for v in report["fixtures"].values())
        if all_ok:
            self.stdout.write(self.style.SUCCESS(f"M1 aceite OK — {note}"))
        else:
            self.stdout.write(self.style.ERROR(f"M1 abaixo de 80% — ver {note}"))
