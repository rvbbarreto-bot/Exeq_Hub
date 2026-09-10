"""Gera comparacao visual DANFE EXEQ vs PDFs de referencia (Desktop/PDFS)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from integrations.sefaz_nfe.danfe.visual_compare import (  # noqa: E402
    DEFAULT_REFERENCE_DIR,
    run_reference_batch,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Comparacao visual DANFE vs PDFs referencia")
    parser.add_argument(
        "--ref-dir",
        type=Path,
        default=DEFAULT_REFERENCE_DIR,
        help="Pasta com PDFs de referencia (default: Desktop/PDFS)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / ".storage" / "danfe_visual_compare",
        help="Saida PNG + index.html + report.json",
    )
    parser.add_argument("--dpi", type=int, default=150)
    args = parser.parse_args()

    reports = run_reference_batch(
        reference_dir=args.ref_dir,
        output_dir=args.out,
        dpi=args.dpi,
    )

    print(f"Comparacoes: {len(reports)}")
    for r in reports:
        ref_cov = f"{r.reference.coverage:.0%}"
        exeq_cov = f"{r.exeq_checklist_coverage:.0%}"
        print(
            f"  {r.reference_path}: ref_markers={ref_cov} "
            f"exeq_checklist={exeq_cov} fixture={r.exeq_fixture} "
            f"pages={len(r.page_pairs)}"
        )
    print(f"HTML: {args.out / 'index.html'}")
    print(f"JSON: {args.out / 'report.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
