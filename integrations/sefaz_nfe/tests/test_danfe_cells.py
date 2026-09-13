"""Testes — celulas MOC (cells.py)."""

from __future__ import annotations

from integrations.sefaz_nfe.danfe.cells import draw_cell


class _FakeCanvas:
    def __init__(self, page_h: float = 841.89):
        self.page_h = page_h
        self.ops: list[str] = []

    def setLineWidth(self, w):
        self.ops.append(f"lw:{w}")

    def rect(self, x, y, w, h):
        self.ops.append(f"rect:{x:.1f},{y:.1f}")

    def setFont(self, name, size):
        self.ops.append(f"font:{name}:{size}")

    def drawString(self, x, y, text):
        self.ops.append(f"text:{text[:20]}")


def test_draw_cell_emits_rect_and_value():
    c = _FakeCanvas()
    draw_cell(
        c,
        left_pt=10,
        top_mm=50,
        width_mm=40,
        height_mm=8,
        page_h=c.page_h,
        label="BASE ICMS",
        value="0,00",
        fonts={"bold": "B", "body": "R"},
    )
    assert any(op.startswith("rect:") for op in c.ops)
    assert any("0,00" in op for op in c.ops)
