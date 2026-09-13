"""Comparacao visual DANFE EXEQ vs PDFs de referencia (ERP/MOC)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

from integrations.sefaz_nfe.danfe.compare import MOC_STRUCTURAL_MARKERS, compare_structural
from integrations.sefaz_nfe.danfe.golden import rasterize_pdf_page
from integrations.sefaz_nfe.danfe.render_moc import LAYOUT_VERSION, render_danfe_moc_pdf

# Marcadores visuais comuns em DANFEs reais (texto extraido do PDF).
REFERENCE_LAYOUT_MARKERS = MOC_STRUCTURAL_MARKERS + (
    "RECEBEMOS DE",
    "CHAVE DE ACESSO",
    "NATUREZA DA OPERACAO",
    "INSCRICAO ESTADUAL",
    "BASE DE CALCULO",
    "VALOR TOTAL",
    "FATURA",
    "TRANSPORTADOR",
    "PROTOCOLO",
    "FOLHA",
)

def default_reference_dir() -> Path:
    """Desktop/PDFS — tenta nomes comuns OneDrive PT/EN."""
    one_drive = Path.home() / "OneDrive"
    for folder in ("Área de Trabalho", "Area de Trabalho", "Desktop"):
        candidate = one_drive / folder / "PDFS"
        if candidate.is_dir():
            return candidate
    return one_drive / "Área de Trabalho" / "PDFS"


DEFAULT_REFERENCE_DIR = default_reference_dir()


@dataclass(frozen=True)
class PdfMarkerReport:
    page_count: int
    width_pt: float
    height_pt: float
    markers: dict[str, bool]

    @property
    def coverage(self) -> float:
        if not self.markers:
            return 0.0
        return sum(1 for v in self.markers.values() if v) / len(self.markers)


@dataclass(frozen=True)
class PageVisualPair:
    reference_name: str
    page_index: int
    side_by_side_path: Path
    reference_only_path: Path
    exeq_only_path: Path


@dataclass(frozen=True)
class VisualCompareReport:
    reference_path: str
    exeq_fixture: str
    layout_version: str
    reference: PdfMarkerReport
    exeq_structural_ok: bool
    exeq_structural_missing: tuple[str, ...]
    exeq_checklist_coverage: float
    exeq_checklist_passed: dict[str, bool]
    page_pairs: tuple[PageVisualPair, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["page_pairs"] = [
            {
                "page_index": p.page_index,
                "side_by_side": str(p.side_by_side_path),
                "reference": str(p.reference_only_path),
                "exeq": str(p.exeq_only_path),
            }
            for p in self.page_pairs
        ]
        return d


def pdf_page_count(pdf_bytes: bytes) -> int:
    import pymupdf

    return len(pymupdf.open(stream=pdf_bytes, filetype="pdf"))


def pdf_page_size_pt(pdf_bytes: bytes, *, page_index: int = 0) -> tuple[float, float]:
    import pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    rect = doc[page_index].rect
    return float(rect.width), float(rect.height)


def analyze_pdf_markers(pdf_bytes: bytes) -> PdfMarkerReport:
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes))
    combined = "\n".join((p.extract_text() or "") for p in reader.pages)
    norm = combined.upper().replace("Ã", "A").replace("Ç", "C").replace("Õ", "O")
    norm_compact = norm.replace(" ", "")
    markers = {}
    for m in REFERENCE_LAYOUT_MARKERS:
        mu = m.upper()
        markers[m] = mu in norm or mu.replace(" ", "") in norm_compact
    w, h = pdf_page_size_pt(pdf_bytes, page_index=0)
    return PdfMarkerReport(
        page_count=len(reader.pages),
        width_pt=w,
        height_pt=h,
        markers=markers,
    )


def build_exeq_candidate_pdfs() -> dict[str, bytes]:
    from integrations.sefaz_nfe.tests.danfe_fixtures import (
        xml_multipage_homolog,
        xml_rich_blocks_homolog,
        xml_with_items,
    )

    return {
        "minimal_1item_homolog": render_danfe_moc_pdf(xml_with_items(1)),
        "rich_blocks_homolog": render_danfe_moc_pdf(xml_rich_blocks_homolog()),
        "multi_2page_homolog": render_danfe_moc_pdf(xml_multipage_homolog(35)),
    }


def pick_exeq_fixture(reference_pages: int) -> str:
    if reference_pages >= 2:
        return "multi_2page_homolog"
    return "rich_blocks_homolog"


def _side_by_side_image(left: Any, right: Any, *, left_label: str, right_label: str) -> Any:
    from PIL import Image, ImageDraw, ImageFont

    gap = 12
    header = 28
    width = left.width + right.width + gap
    height = max(left.height, right.height) + header
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(left.convert("RGB"), (0, header))
    canvas.paste(right.convert("RGB"), (left.width + gap, header))
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    draw.text((4, 6), left_label, fill="black", font=font)
    draw.text((left.width + gap + 4, 6), right_label, fill="black", font=font)
    return canvas


def compare_reference_to_exeq(
    reference_pdf: bytes,
    exeq_pdf: bytes,
    *,
    reference_name: str,
    exeq_fixture: str,
    output_dir: Path,
    dpi: int = 150,
) -> VisualCompareReport:
    from integrations.sefaz_nfe.danfe.checklist import evaluate_danfe_checklist
    from integrations.sefaz_nfe.tests.danfe_fixtures import (
        xml_multipage_homolog,
        xml_rich_blocks_homolog,
        xml_with_items,
    )

    xml_by_fixture = {
        "minimal_1item_homolog": xml_with_items(1),
        "rich_blocks_homolog": xml_rich_blocks_homolog(),
        "multi_2page_homolog": xml_multipage_homolog(35),
    }
    xml_bytes = xml_by_fixture[exeq_fixture]

    ref_report = analyze_pdf_markers(reference_pdf)
    structural = compare_structural(exeq_pdf)
    checklist = evaluate_danfe_checklist(xml_bytes)

    out = output_dir / reference_name
    out.mkdir(parents=True, exist_ok=True)

    ref_pages = pdf_page_count(reference_pdf)
    exeq_pages = pdf_page_count(exeq_pdf)
    pairs: list[PageVisualPair] = []

    for page_index in range(ref_pages):
        ref_img = rasterize_pdf_page(reference_pdf, dpi=dpi, page_index=page_index)
        ref_only = out / f"p{page_index}.reference.dpi{dpi}.png"
        ref_img.save(ref_only, format="PNG", optimize=True)

        if page_index < exeq_pages:
            exeq_img = rasterize_pdf_page(exeq_pdf, dpi=dpi, page_index=page_index)
            exeq_only = out / f"p{page_index}.exeq_{exeq_fixture}.dpi{dpi}.png"
            exeq_img.save(exeq_only, format="PNG", optimize=True)
            combined = _side_by_side_image(
                ref_img,
                exeq_img,
                left_label=f"REF {reference_name} p{page_index + 1}",
                right_label=f"EXEQ {exeq_fixture} p{page_index + 1}",
            )
            side_path = out / f"p{page_index}.side_by_side.dpi{dpi}.png"
            combined.save(side_path, format="PNG", optimize=True)
            pairs.append(
                PageVisualPair(
                    reference_name=reference_name,
                    page_index=page_index,
                    side_by_side_path=side_path,
                    reference_only_path=ref_only,
                    exeq_only_path=exeq_only,
                )
            )

    return VisualCompareReport(
        reference_path=reference_name,
        exeq_fixture=exeq_fixture,
        layout_version=LAYOUT_VERSION,
        reference=ref_report,
        exeq_structural_ok=structural.ok,
        exeq_structural_missing=structural.missing,
        exeq_checklist_coverage=checklist.coverage,
        exeq_checklist_passed=checklist.passed,
        page_pairs=tuple(pairs),
    )


def run_reference_batch(
    *,
    reference_dir: Path | None = None,
    output_dir: Path | None = None,
    dpi: int = 150,
) -> list[VisualCompareReport]:
    ref_dir = reference_dir or DEFAULT_REFERENCE_DIR
    out_root = output_dir or (Path.cwd() / ".storage" / "danfe_visual_compare")
    out_root.mkdir(parents=True, exist_ok=True)

    if not ref_dir.is_dir():
        raise FileNotFoundError(f"Diretorio de referencia nao encontrado: {ref_dir}")

    pdfs = sorted(ref_dir.glob("*.pdf"))
    if not pdfs:
        raise FileNotFoundError(f"Nenhum PDF em {ref_dir}")

    exeq_candidates = build_exeq_candidate_pdfs()
    reports: list[VisualCompareReport] = []

    for pdf_path in pdfs:
        ref_bytes = pdf_path.read_bytes()
        fixture = pick_exeq_fixture(pdf_page_count(ref_bytes))
        exeq_pdf = exeq_candidates[fixture]
        slug = pdf_path.stem.replace(" ", "_")[:80]
        reports.append(
            compare_reference_to_exeq(
                ref_bytes,
                exeq_pdf,
                reference_name=slug,
                exeq_fixture=fixture,
                output_dir=out_root,
                dpi=dpi,
            )
        )

    summary_path = out_root / "report.json"
    summary_path.write_text(
        json.dumps([r.to_dict() for r in reports], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_html_report(out_root, reports)
    return reports


def _write_html_report(output_dir: Path, reports: list[VisualCompareReport]) -> None:
    rows = []
    for r in reports:
        for pair in r.page_pairs:
            rel = pair.side_by_side_path.relative_to(output_dir).as_posix()
            rows.append(
                f"<tr><td>{r.reference_path}</td><td>{r.exeq_fixture}</td>"
                f"<td>{pair.page_index + 1}</td>"
                f"<td><a href='{rel}'><img src='{rel}' width='480'/></a></td></tr>"
            )
    html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8"/>
<title>DANFE visual compare — EXEQ vs referencia</title>
<style>
body {{ font-family: sans-serif; margin: 1rem; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #ccc; padding: 8px; vertical-align: top; }}
.meta {{ background: #f5f5f5; padding: 12px; margin-bottom: 16px; }}
</style></head><body>
<h1>Comparacao visual DANFE</h1>
<div class="meta">
<p>Layout EXEQ: <strong>{LAYOUT_VERSION}</strong></p>
<p>Esquerda = PDF referencia (ERP). Direita = EXEQ (fixture homolog).</p>
<p>Relatorio JSON: <a href="report.json">report.json</a></p>
</div>
<table>
<tr><th>Referencia</th><th>Fixture EXEQ</th><th>Pagina</th><th>Side-by-side</th></tr>
{''.join(rows)}
</table>
</body></html>"""
    (output_dir / "index.html").write_text(html, encoding="utf-8")
