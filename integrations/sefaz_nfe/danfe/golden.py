"""Golden PDF / visual regression — rasterização e comparação (Phase 4 §31)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GOLDEN_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "danfe_golden"


@dataclass(frozen=True)
class GoldenCompareResult:
    name: str
    page_index: int
    dpi: int
    diff_ratio: float
    passed: bool
    reference_path: Path
    actual_size: tuple[int, int]
    reference_size: tuple[int, int]


def rasterize_pdf_page(pdf_bytes: bytes, *, dpi: int = 150, page_index: int = 0) -> Any:
    import pymupdf
    from integrations.sefaz_nfe.danfe.barcode_decode import _pil_from_pixmap

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    if page_index >= len(doc):
        raise IndexError(f"page_index {page_index} fora do PDF ({len(doc)} páginas)")
    pix = doc[page_index].get_pixmap(dpi=dpi, alpha=False)
    return _pil_from_pixmap(pix)


def pdf_sha256(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()


def image_diff_ratio(actual: Any, reference: Any) -> float:
    """Diferença média normalizada 0..1 (tolerante a anti-aliasing)."""
    from PIL import Image, ImageChops, ImageStat

    if actual.size != reference.size:
        reference = reference.resize(actual.size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(actual.convert("RGB"), reference.convert("RGB"))
    stat = ImageStat.Stat(diff)
    # mean per channel / 255
    return sum(stat.mean) / (3.0 * 255.0)


def golden_png_path(name: str, *, page_index: int = 0, dpi: int = 150) -> Path:
    return GOLDEN_DIR / f"{name}.p{page_index}.dpi{dpi}.png"


def compare_page_to_golden(
    pdf_bytes: bytes,
    name: str,
    *,
    page_index: int = 0,
    dpi: int = 150,
    tolerance: float = 0.035,
    update: bool = False,
) -> GoldenCompareResult:
    ref_path = golden_png_path(name, page_index=page_index, dpi=dpi)
    actual = rasterize_pdf_page(pdf_bytes, dpi=dpi, page_index=page_index)

    if update:
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        actual.save(ref_path, format="PNG", optimize=True)
        return GoldenCompareResult(
            name=name,
            page_index=page_index,
            dpi=dpi,
            diff_ratio=0.0,
            passed=True,
            reference_path=ref_path,
            actual_size=actual.size,
            reference_size=actual.size,
        )

    if not ref_path.is_file():
        return GoldenCompareResult(
            name=name,
            page_index=page_index,
            dpi=dpi,
            diff_ratio=1.0,
            passed=False,
            reference_path=ref_path,
            actual_size=actual.size,
            reference_size=(0, 0),
        )

    from PIL import Image

    reference = Image.open(ref_path)
    ratio = image_diff_ratio(actual, reference)
    return GoldenCompareResult(
        name=name,
        page_index=page_index,
        dpi=dpi,
        diff_ratio=ratio,
        passed=ratio <= tolerance,
        reference_path=ref_path,
        actual_size=actual.size,
        reference_size=reference.size,
    )


def compare_pdf_to_golden(
    pdf_bytes: bytes,
    name: str,
    *,
    dpi: int = 150,
    tolerance: float = 0.035,
    update: bool = False,
) -> list[GoldenCompareResult]:
    import pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    results: list[GoldenCompareResult] = []
    for page_index in range(len(doc)):
        results.append(
            compare_page_to_golden(
                pdf_bytes,
                name,
                page_index=page_index,
                dpi=dpi,
                tolerance=tolerance,
                update=update,
            )
        )
    return results
