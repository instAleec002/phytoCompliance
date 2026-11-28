"""Native DOCX and XLSX extractors and the full pipeline on them: both routes give the same section paths (structure
is exact in Office files), blocks have no page, and chunks carry the configuration signature."""
from docx import Document
from openpyxl import Workbook

from knowledge.documents import Pipeline, load_config
from knowledge.documents.registry import EXTRACTORS


def make_docx(path):
    d = Document()
    d.core_properties.title = "Procedimiento de aplicación"
    d.add_heading("Procedimiento de aplicación", level=0)
    d.add_heading("1. Preparación", level=1)
    d.add_paragraph("Calibrar el equipo antes de cada aplicación. Verificar las boquillas.")
    d.add_paragraph("Revisar la etiqueta", style="List Bullet")
    d.add_paragraph("Registrar la dosis", style="List Bullet")
    d.add_heading("1.1 Dosis por producto", level=2)
    t = d.add_table(rows=3, cols=3)
    for c, text in enumerate(["Producto", "Dosis", "Carencia"]):
        t.cell(0, c).text = text
    t.cell(1, 0).text, t.cell(1, 1).text, t.cell(1, 2).text = "ALINA", "1 L/ha", "30"
    merged = t.cell(2, 0).merge(t.cell(2, 1))
    merged.text = "Nota común"
    t.cell(2, 2).text = "-"
    d.save(path)


def test_docx_extractor_reads_headings_lists_and_merged_cells(tmp_path):
    p = tmp_path / "proc.docx"
    make_docx(p)
    doc = EXTRACTORS.create("docx").structured(p, "x")
    kinds = [(b.kind, b.level) for b in doc.blocks]
    assert kinds[:4] == [("heading", 1), ("heading", 1), ("paragraph", None), ("list_item", 1)]
    assert doc.title == "Procedimiento de aplicación" and all(b.page is None for b in doc.blocks)
    table = next(b for b in doc.blocks if b.kind == "table")
    note = next(c for c in table.cells if c.text == "Nota común")
    assert (note.row, note.col, note.col_span) == (3, 1, 2)


def test_xlsx_extractor_sheet_heading_and_merged_ranges(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Umbrales"
    ws.append(["Plaga", "Umbral", "Acción"])
    ws.append(["Botrytis", "5 %", "Aplicar"])
    ws.append(["Nota general", None, None])
    ws.merge_cells("A3:C3")
    p = tmp_path / "umbrales.xlsx"
    wb.save(p)
    doc = EXTRACTORS.create("xlsx").structured(p, "x")
    assert [b.kind for b in doc.blocks] == ["heading", "table"] and doc.blocks[0].text == "Umbrales"
    note = next(c for c in doc.blocks[1].cells if c.text == "Nota general")
    assert note.col_span == 3


def test_pipeline_routes_agree_on_office_structure(tmp_path):
    p = tmp_path / "proc.docx"
    make_docx(p)
    results = {r: Pipeline(load_config(env=False, route=r)).process(p, "proc") for r in ("markdown", "structured", "mixed")}
    sections = {r: [c.section for c in res.chunks] for r, res in results.items()}
    assert sections["markdown"] == sections["structured"] == sections["mixed"]
    assert ("1. Preparación", "1.1 Dosis por producto") in sections["structured"]
    chunk = results["structured"].chunks[0]
    assert chunk.pages == () and chunk.meta["signature"] and chunk.header.startswith("Documento: Procedimiento")
