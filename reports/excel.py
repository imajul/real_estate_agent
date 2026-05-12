"""Export flipping analysis results to Excel."""

from datetime import datetime
from typing import Optional
import openpyxl
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers
)
from openpyxl.utils import get_column_letter

from models import FlippingAnalysis, MarketReference


# Color palette
CLR_HEADER      = "1B2A4A"   # dark navy
CLR_SUBHEADER   = "2E4A7A"
CLR_BUY         = "1A7A3C"   # green
CLR_WATCH       = "B8860B"   # dark gold
CLR_SKIP        = "8B0000"   # dark red
CLR_ROW_ALT     = "F0F4FA"   # light blue-grey
CLR_WHITE       = "FFFFFF"

_thin = Side(style="thin", color="CCCCCC")
_border = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)


def _hdr_font(color: str = CLR_WHITE, sz: int = 11, bold: bool = True) -> Font:
    return Font(name="Calibri", size=sz, bold=bold, color=color)


def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


def _center(wrap: bool = False) -> Alignment:
    return Alignment(horizontal="center", vertical="center", wrap_text=wrap)


def _left(wrap: bool = False) -> Alignment:
    return Alignment(horizontal="left", vertical="center", wrap_text=wrap)


def _rec_color(rec: str) -> str:
    if rec == "COMPRAR":
        return CLR_BUY
    if rec == "ANALIZAR MÁS":
        return CLR_WATCH
    return CLR_SKIP


def _set_col_widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _write_header_row(ws, row: int, headers: list[str], bg: str = CLR_HEADER) -> None:
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.font = _hdr_font()
        cell.fill = _fill(bg)
        cell.alignment = _center(wrap=True)
        cell.border = _border


def _fmt(val, fmt: str = "") -> str:
    if val is None:
        return "—"
    if fmt == "usd":
        return f"USD {val:,.0f}"
    if fmt == "pct":
        return f"{val:+.1f}%"
    if fmt == "score":
        return f"{val:.1f}/10"
    return str(val)


# ── Sheet 1: Summary ─────────────────────────────────────────────────────────

def _build_summary(wb: openpyxl.Workbook, analyses: list[FlippingAnalysis],
                   market_ref: MarketReference, neighborhood: str, total_props: int) -> None:
    ws = wb.active
    ws.title = "Resumen"
    ws.sheet_view.showGridLines = False

    # Title
    ws.merge_cells("A1:G1")
    title_cell = ws["A1"]
    title_cell.value = f"Análisis de Flipping — {neighborhood.title()}"
    title_cell.font = Font(name="Calibri", size=16, bold=True, color=CLR_WHITE)
    title_cell.fill = _fill(CLR_HEADER)
    title_cell.alignment = _center()
    ws.row_dimensions[1].height = 32

    # Subtitle
    ws.merge_cells("A2:G2")
    sub = ws["A2"]
    sub.value = f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}  |  Propiedades analizadas: {len(analyses)} de {total_props} encontradas"
    sub.font = Font(name="Calibri", size=10, color=CLR_WHITE)
    sub.fill = _fill(CLR_SUBHEADER)
    sub.alignment = _center()
    ws.row_dimensions[2].height = 18

    # Market ref block
    ws.merge_cells("A3:G3")
    mref = ws["A3"]
    mref.value = (
        f"Referencia de mercado — Mediana: USD {market_ref.median_price_per_m2_usd:,.0f}/m²  |  "
        f"Rango: USD {market_ref.min_price_per_m2_usd:,.0f} – {market_ref.max_price_per_m2_usd:,.0f}/m²  |  "
        f"Muestra: {market_ref.sample_count} propiedades"
    )
    mref.font = Font(name="Calibri", size=10, bold=True, color="1B2A4A")
    mref.fill = _fill("D6E4F7")
    mref.alignment = _center()
    ws.row_dimensions[3].height = 18

    # Column headers
    headers = ["#", "Dirección", "Precio (USD)", "m² total", "USD/m²",
               "Desc. vs mercado", "Score", "Recomendación", "URL"]
    _write_header_row(ws, 4, headers)
    ws.row_dimensions[4].height = 22

    _set_col_widths(ws, [4, 35, 14, 10, 10, 16, 9, 16, 50])

    # Data rows
    for i, a in enumerate(analyses, 1):
        row = 4 + i
        alt = row % 2 == 0
        bg = CLR_ROW_ALT if alt else CLR_WHITE
        rec_color = _rec_color(a.flipping_recommendation)

        p = a.property
        price_m2 = (p.price_usd / p.surface_total) if p.price_usd and p.surface_total else None

        values = [
            i,
            p.address,
            _fmt(p.price_usd, "usd"),
            _fmt(p.surface_total),
            _fmt(price_m2, "usd"),
            _fmt(a.discount_vs_market_pct, "pct"),
            _fmt(a.flipping_score, "score"),
            a.flipping_recommendation or "—",
            p.url,
        ]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = _border
            cell.font = Font(name="Calibri", size=10)
            cell.alignment = _left(wrap=False)
            if col == 8:  # Recomendación
                cell.fill = _fill(rec_color)
                cell.font = Font(name="Calibri", size=10, bold=True, color=CLR_WHITE)
                cell.alignment = _center()
            elif col == 9:  # URL — hyperlink style
                cell.font = Font(name="Calibri", size=10, color="1155CC", underline="single")
                cell.hyperlink = p.url
            else:
                cell.fill = _fill(bg)

        ws.row_dimensions[row].height = 16

    # Freeze header rows
    ws.freeze_panes = "A5"


# ── Sheet 2: Detail ──────────────────────────────────────────────────────────

def _build_detail(wb: openpyxl.Workbook, analyses: list[FlippingAnalysis]) -> None:
    ws = wb.create_sheet("Detalle")
    ws.sheet_view.showGridLines = False

    ws.merge_cells("A1:F1")
    t = ws["A1"]
    t.value = "Detalle de análisis por propiedad"
    t.font = Font(name="Calibri", size=14, bold=True, color=CLR_WHITE)
    t.fill = _fill(CLR_HEADER)
    t.alignment = _center()
    ws.row_dimensions[1].height = 28

    _set_col_widths(ws, [4, 24, 18, 18, 18, 60])

    current_row = 2
    for i, a in enumerate(analyses, 1):
        p = a.property
        rec_color = _rec_color(a.flipping_recommendation)

        # Property header
        ws.merge_cells(f"A{current_row}:F{current_row}")
        h = ws.cell(row=current_row, column=1,
                    value=f"#{i}  {p.address}  —  {a.flipping_recommendation or ''}")
        h.font = Font(name="Calibri", size=11, bold=True, color=CLR_WHITE)
        h.fill = _fill(rec_color)
        h.alignment = _left()
        ws.row_dimensions[current_row].height = 20
        current_row += 1

        # Key figures row
        figures = [
            ("Precio", _fmt(p.price_usd, "usd")),
            ("m² total", _fmt(p.surface_total)),
            ("USD/m²", _fmt((p.price_usd / p.surface_total) if p.price_usd and p.surface_total else None, "usd")),
            ("Desc. mercado", _fmt(a.discount_vs_market_pct, "pct")),
            ("Score flipping", _fmt(a.flipping_score, "score")),
            ("ROI estimado", _fmt(a.roi_pct, "pct")),
        ]
        for col, (label, val) in enumerate(figures, 1):
            lc = ws.cell(row=current_row, column=col, value=label)
            lc.font = _hdr_font(color="1B2A4A", sz=9)
            lc.fill = _fill("D6E4F7")
            lc.alignment = _center()
            lc.border = _border
            vc = ws.cell(row=current_row + 1, column=col, value=val)
            vc.font = Font(name="Calibri", size=10, bold=True)
            vc.alignment = _center()
            vc.border = _border
            vc.fill = _fill(CLR_ROW_ALT)
        current_row += 2

        # AI Summary
        if a.ai_summary:
            ws.merge_cells(f"A{current_row}:F{current_row}")
            sc = ws.cell(row=current_row, column=1, value=f"Resumen IA: {a.ai_summary}")
            sc.font = Font(name="Calibri", size=9, italic=True)
            sc.alignment = _left(wrap=True)
            sc.fill = _fill(CLR_WHITE)
            ws.row_dimensions[current_row].height = 48
            current_row += 1

        # Pros / cons
        pros_text = " • ".join(a.pros) if a.pros else "—"
        cons_text = " • ".join(a.cons) if a.cons else "—"
        for label, text, color in [
            ("✅ Pros", pros_text, "E8F5E9"),
            ("❌ Contras", cons_text, "FFEBEE"),
        ]:
            ws.merge_cells(f"A{current_row}:F{current_row}")
            cell = ws.cell(row=current_row, column=1, value=f"{label}: {text}")
            cell.font = Font(name="Calibri", size=9)
            cell.alignment = _left(wrap=True)
            cell.fill = _fill(color)
            ws.row_dimensions[current_row].height = 32
            current_row += 1

        # Spacer
        ws.row_dimensions[current_row].height = 8
        current_row += 1

    ws.freeze_panes = "A2"


# ── Public API ────────────────────────────────────────────────────────────────

def export_excel(
    analyses: list[FlippingAnalysis],
    market_ref: MarketReference,
    neighborhood: str,
    total_props: int,
    output_path: str,
) -> None:
    """Write the full analysis report to an Excel file at output_path."""
    wb = openpyxl.Workbook()
    _build_summary(wb, analyses, market_ref, neighborhood, total_props)
    _build_detail(wb, analyses)
    wb.save(output_path)
