"""Small document builders for tests (PDF, DOCX, XLSX written to a temp folder)."""
from __future__ import annotations

import io
from pathlib import Path


def make_pdf(path: Path, pages: list[str]) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    for text in pages:
        y = 800
        for line in text.split("\n"):
            if line:
                c.drawString(50, y, line)
            y -= 16
        c.showPage()
    c.save()
    return path


def make_blank_pdf(path: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    c.rect(50, 50, 200, 200, fill=1)
    c.showPage()
    c.save()
    return path


def make_docx(path: Path, blocks: list[tuple]) -> Path:
    """blocks: ("h1", text) / ("h2", text) / ("p", text) / ("table", rows)"""
    from docx import Document

    d = Document()
    for kind, value in blocks:
        if kind.startswith("h"):
            d.add_heading(value, level=int(kind[1:]))
        elif kind == "p":
            d.add_paragraph(value)
        elif kind == "table":
            table = d.add_table(rows=0, cols=len(value[0]))
            for row in value:
                for cell, text in zip(table.add_row().cells, row):
                    cell.text = text
    d.save(str(path))
    return path


def make_xlsx(path: Path, sheets: dict[str, list[list]], hidden: tuple[str, ...] = ()) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
        if title in hidden:
            ws.sheet_state = "hidden"
    wb.save(str(path))
    return path


def upload(service, path: Path, by: str = "Admin", process: bool = True):
    """Upload like the Documents page does; ``process`` also runs the ingestion step at once."""
    with path.open("rb") as fh:
        result = service.upload(path.name, fh, path.stat().st_size, uploaded_by=by)
    if process:
        service.process(result.name)
    return result


def bytes_io(data: bytes) -> io.BytesIO:
    return io.BytesIO(data)
