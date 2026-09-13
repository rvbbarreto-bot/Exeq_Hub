"""Calibração visual — extração de linhas verticais de PNG referência (UniDANFE)."""

from __future__ import annotations

from pathlib import Path

# Manter em sync com layout.MARGIN_* (evita import circular layout ↔ calibrate)
_MARGIN_LEFT_MM = 2.5
_PAGE_CONTENT_WIDTH_MM = 210.0 - _MARGIN_LEFT_MM - 2.5

# Larguras derivadas de CONSTRUFORTI_NF_3925 @ 150dpi, escaladas para content_width_mm() ≈ 205mm.
# Faixas Y (mm): dest 85.8–111.3, tax 127.8–144.8, transport 149.0–164.3 (label band).


def measure_vertical_grid_widths_mm(
    png_path: Path | str,
    *,
    y_top_mm: float,
    y_bottom_mm: float,
    dpi: int = 150,
    threshold_ratio: float = 0.55,
    min_col_width_mm: float = 5.0,
) -> tuple[float, ...]:
    """Retorna larguras de colunas (mm) entre linhas verticais detectadas."""
    from PIL import Image

    mm_per_px = 25.4 / dpi
    left_margin_px = _MARGIN_LEFT_MM / mm_per_px

    img = Image.open(png_path).convert("L")
    w, h = img.size
    px = img.load()
    y0 = int(y_top_mm / mm_per_px)
    y1 = min(int(y_bottom_mm / mm_per_px), h)
    span = max(y1 - y0, 1)

    col_sum = [0] * w
    for x in range(w):
        for y in range(y0, y1):
            if px[x, y] < 128:
                col_sum[x] += 1

    th = span * threshold_ratio
    peaks = [x for x in range(int(w * 0.03), int(w * 0.97)) if col_sum[x] >= th]
    clusters: list[list[int]] = []
    for p in peaks:
        if clusters and p - clusters[-1][-1] <= 2:
            clusters[-1].append(p)
        else:
            clusters.append([p])

    centers = [sum(c) // len(c) for c in clusters]
    offsets_mm = [(c - left_margin_px) * mm_per_px for c in centers]
    if len(offsets_mm) < 2:
        return ()
    widths = [offsets_mm[i + 1] - offsets_mm[i] for i in range(len(offsets_mm) - 1)]
    return tuple(round(width, 1) for width in widths if width >= min_col_width_mm)


def scale_widths_to_content(widths: tuple[float, ...]) -> tuple[float, ...]:
    total = sum(widths)
    if total <= 0:
        return widths
    target = _PAGE_CONTENT_WIDTH_MM
    factor = target / total
    scaled = [round(w * factor, 1) for w in widths]
    drift = round(target - sum(scaled), 1)
    if scaled and drift:
        scaled[-1] = round(scaled[-1] + drift, 1)
    return tuple(scaled)


def split_width(width: float, ratio_left: float) -> tuple[float, float]:
    left = round(width * ratio_left, 1)
    return left, round(width - left, 1)


# --- Produtos (faixa y 178–192 mm) ---
CONSTRUFORTI_PRODUCT_WIDTHS_RAW_MM: tuple[float, ...] = (
    11.7,
    77.2,
    11.7,
    8.5,
    7.1,
    7.1,
    9.2,
    9.0,
    8.8,
    9.3,
    9.0,
    7.3,
    12.4,
)

# --- Destinatário (medição + split alinhado à linha 1) ---
CONSTRUFORTI_DEST_ROW1_RAW_MM: tuple[float, ...] = (116.3, 36.1, 35.7)

# Row2/3: proporções legíveis (50/25/15/10 e 35/20/5/20/10) sobre ~188 mm
CONSTRUFORTI_DEST_ROW2_RAW_MM: tuple[float, ...] = (94.0, 47.0, 28.2, 18.9)
CONSTRUFORTI_DEST_ROW3_RAW_MM: tuple[float, ...] = (65.8, 37.6, 9.4, 37.6, 37.7)

# --- Entrega (mesma grade dest, linha 2 com CEP/Município/UF) ---
_del_tail = split_width(35.7, 18.0 / (18.0 + 17.7))
CONSTRUFORTI_DELIVERY_ROW2_RAW_MM: tuple[float, ...] = (
    100.8,
    50.6,
    _del_tail[0],
    12.5,
    6.2,
)

# --- Impostos ---
CONSTRUFORTI_TAX_ROW1_RAW_MM: tuple[float, ...] = (31.5, 31.5, 31.5, 31.5, 62.1)
CONSTRUFORTI_TAX_ROW2_MEASURED_RAW_MM: tuple[float, ...] = (80.4, 23.5, 21.7, 20.3, 7.5, 34.9)
# 7 colunas equilibradas (medição bruta agrupa células vazias na col 1)
CONSTRUFORTI_TAX_ROW2_RAW_MM: tuple[float, ...] = (26.9, 26.9, 26.9, 26.9, 26.9, 26.9, 26.7)

# --- Transporte (proporções UniDANFE CONSTRUFORTI; label band y 149–161 mm) ---
CONSTRUFORTI_TRANSPORT_ROW1_RAW_MM: tuple[float, ...] = (84.6, 28.2, 18.8, 18.8, 9.4, 28.3)
CONSTRUFORTI_TRANSPORT_ROW2_RAW_MM: tuple[float, ...] = (94.0, 65.8, 9.4, 18.9)
CONSTRUFORTI_TRANSPORT_ROW3_RAW_MM: tuple[float, ...] = (31.4, 31.4, 31.4, 31.4, 31.3, 31.2)

ITEM_COL_WIDTHS_CONSTRUFORTI_MM = scale_widths_to_content(CONSTRUFORTI_PRODUCT_WIDTHS_RAW_MM)
DEST_ROW1_WIDTHS_CONSTRUFORTI_MM = scale_widths_to_content(CONSTRUFORTI_DEST_ROW1_RAW_MM)
DEST_ROW2_WIDTHS_CONSTRUFORTI_MM = scale_widths_to_content(CONSTRUFORTI_DEST_ROW2_RAW_MM)
DEST_ROW3_WIDTHS_CONSTRUFORTI_MM = scale_widths_to_content(CONSTRUFORTI_DEST_ROW3_RAW_MM)
DELIVERY_ROW1_WIDTHS_CONSTRUFORTI_MM = DEST_ROW1_WIDTHS_CONSTRUFORTI_MM
DELIVERY_ROW2_WIDTHS_CONSTRUFORTI_MM = scale_widths_to_content(CONSTRUFORTI_DELIVERY_ROW2_RAW_MM)
TAX_ROW1_WIDTHS_CONSTRUFORTI_MM = scale_widths_to_content(CONSTRUFORTI_TAX_ROW1_RAW_MM)
TAX_ROW2_WIDTHS_CONSTRUFORTI_MM = scale_widths_to_content(CONSTRUFORTI_TAX_ROW2_RAW_MM)
TRANSPORT_ROW1_WIDTHS_CONSTRUFORTI_MM = scale_widths_to_content(CONSTRUFORTI_TRANSPORT_ROW1_RAW_MM)
TRANSPORT_ROW2_WIDTHS_CONSTRUFORTI_MM = scale_widths_to_content(CONSTRUFORTI_TRANSPORT_ROW2_RAW_MM)
TRANSPORT_ROW3_WIDTHS_CONSTRUFORTI_MM = scale_widths_to_content(CONSTRUFORTI_TRANSPORT_ROW3_RAW_MM)

CONSTRUFORTI_CALIBRATION_BANDS: dict[str, tuple[float, float, int]] = {
    "dest_r1": (85.8, 94.3, 3),
    "dest_r2": (94.3, 102.8, 4),
    "dest_r3": (102.8, 111.3, 5),
    "tax_r1": (127.8, 136.3, 5),
    "tax_r2": (136.3, 144.8, 7),
    "trans_r1": (149.0, 157.5, 6),
    "trans_r2": (157.5, 166.0, 4),
    "trans_r3": (166.0, 174.5, 6),
}
