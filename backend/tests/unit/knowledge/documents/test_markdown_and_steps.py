"""Markdown round trip and the engine-independent steps, on small hand-made documents."""
from knowledge.documents.markdown import parse_markdown, render_markdown
from knowledge.documents.model import Block, Cell, MarkdownDocument, NormalizedDocument
from knowledge.documents.registry import STEPS
from knowledge.documents.steps.outline import depth, numbering


def doc(blocks, pages=None, title="Manual de prueba"):
    return NormalizedDocument(doc_id="d1", title=title, source_format="pdf", blocks=tuple(blocks), pages=pages)


def run(step, d, **opts):
    return STEPS.create(step, **opts)(d)


# Markdown ------------------------------------------------------------------------------------------------------------

def test_markdown_round_trip_keeps_kinds_pages_levels_and_tables():
    cells = (Cell("Plaga", 1, 1, header=True), Cell("Umbral", 1, 2, header=True), Cell("Botrytis", 2, 1), Cell("5 %", 2, 2))
    d = doc([Block("heading", "IV. Manejo", 1, 1), Block("paragraph", "Texto uno.", 1),
             Block("list_item", "primero", 2, 1), Block("list_item", "anidado", 2, 2),
             Block("table", "", 2, cells=cells), Block("caption", "Tabla 1. Umbrales", 2)])
    back = parse_markdown(render_markdown(d))
    assert [(b.kind, b.page, b.level) for b in back] == [
        ("heading", 1, 1), ("paragraph", 1, None), ("list_item", 2, 1), ("list_item", 2, 2), ("table", 2, None),
        ("caption", 2, None)]
    table = back[4]
    assert [c.text for c in table.cells] == ["Plaga", "Umbral", "Botrytis", "5 %"]
    assert all(c.header for c in table.cells if c.row == 1)


def test_markdown_pages_from_items_and_anchors_and_bold_mark():
    md = MarkdownDocument("d", "t", "pdf", pages=("# Uno\n\n**Título en negrita**", "texto de la *segunda* página"))
    blocks = parse_markdown(md)
    assert [(b.kind, b.page) for b in blocks] == [("heading", 1), ("paragraph", 1), ("paragraph", 2)]
    assert blocks[1].meta == {"bold": True} and blocks[1].text == "Título en negrita"
    assert blocks[2].text == "texto de la segunda página"
    anchored = parse_markdown(MarkdownDocument("d", "t", "pdf", pages=("<!-- page 7 -->\n\nhola",), paged=False))
    assert anchored[0].page == 7


# Text and furniture --------------------------------------------------------------------------------------------------

def test_text_step_fixes_symbol_font_ligatures_cut_words_and_breaks():
    bullet, fi_ligature = chr(0xF0B7), chr(0xFB01)          # Symbol-font bullet and the «fi» ligature
    d = doc([Block("paragraph", f"{bullet} e{fi_ligature}cacia del fungi- cida<br>contra Botrytis", 1)])
    assert run("text", d).blocks[0].text == "• eficacia del fungicida contra Botrytis"


def test_furniture_drops_running_headers_page_numbers_and_page_of():
    blocks = []
    for p in range(1, 6):
        blocks += [Block("paragraph", "INIA - Manual técnico 2026", p), Block("paragraph", f"Contenido de la página {p}.", p),
                   Block("paragraph", str(p), p)]
    blocks.append(Block("paragraph", "Fin del manual. Página 5 de 5", 5))
    out = run("furniture", doc(blocks, pages=5))
    texts = [b.text for b in out.blocks]
    assert "INIA - Manual técnico 2026" not in texts and "3" not in texts
    assert texts[-1] == "Fin del manual."
    assert {x["reason"] for x in out.meta["dropped"]} <= {"se repite en muchas páginas", "número de página"}
    assert not any(t.isdigit() for t in texts)
    lone = run("furniture", doc([Block("paragraph", "Texto.", 1), Block("paragraph", "- 12 -", 1)], pages=1))
    assert lone.meta["dropped"][0]["reason"] == "número de página"


# Tables --------------------------------------------------------------------------------------------------------------

def test_layout_table_becomes_paragraphs_and_split_table_is_merged():
    layout = Block("table", "", 1, cells=(Cell("1.0", 1, 1), Cell("ALCANCE", 1, 2)) + tuple(Cell("", 1, c) for c in range(3, 12)))
    head = (Cell("Ingrediente", 1, 1, header=True), Cell("LMR", 1, 2, header=True))
    t1 = Block("table", "", 2, cells=head + (Cell("boscalid", 2, 1), Cell("15", 2, 2)))
    t2 = Block("table", "", 3, cells=head + (Cell("fludioxonil", 2, 1), Cell("3", 2, 2)))
    out = run("tables", doc([layout, t1, t2])).blocks
    assert out[0].kind == "paragraph" and out[0].text == "1.0 ALCANCE"
    assert len(out) == 2 and out[1].meta["pages"] == [2, 3]
    assert [c.text for c in out[1].cells if c.col == 1] == ["Ingrediente", "boscalid", "fludioxonil"]


# Outline -------------------------------------------------------------------------------------------------------------

def test_numbering_and_depth_ignore_trailing_zero():
    assert numbering("IV.- Manejo integrado") == ("roman", "IV", 4)
    assert numbering("4.1.2 Control químico") == ("decimal", "4.1.2", 4)
    assert numbering("a. Objetivo") == ("letter", "a", 1)
    assert numbering("Manejo sin número") is None
    assert depth("8.0") == 1 and depth("8.1") == 2 and depth("8.1.0") == 2


def test_outline_drops_toc_page_sets_levels_splits_inline_titles_and_title_level_zero():
    blocks = [Block("heading", "MANUAL DE MANEJO", 1, 1)]
    blocks += [Block("list_item", t, 2, 1) for t in ("I.- Plaga", "II.- Umbrales", "2.1. Muestreo", "III.- Control")]
    blocks += [Block("list_item", "I.- Plaga.- Organismo que causa daño económico a los cultivos de exportación.", 3, 1),
               Block("heading", "II.- Umbrales", 4, 3), Block("heading", "2.1. Muestreo", 4, 3),
               Block("paragraph", "Se toman veinte plantas por sitio de muestreo.", 4),
               Block("heading", "III.- Control", 5, 3),
               Block("list_item", "1. Kogan, M 1998. Integrated pest management.", 5, 1)]
    out = run("outline", doc(blocks, pages=5))
    heads = [(b.level, b.text) for b in out.blocks if b.kind == "heading"]
    assert heads == [(0, "MANUAL DE MANEJO"), (1, "I.- Plaga.-"), (1, "II.- Umbrales"), (2, "2.1. Muestreo"),
                     (1, "III.- Control")]
    assert all(x["reason"] == "página de índice" for x in out.meta["dropped"]) and len(out.meta["dropped"]) == 4
    assert out.blocks[2].text.startswith("Organismo que causa")
    assert out.blocks[-1].kind == "list_item"                     # «1. Kogan…» is not a section of chapter III


def test_outline_demotes_implausible_numbers_and_scopes_restarted_annex():
    blocks = [Block("heading", "1.0 Introducción", 1, 2), Block("heading", "2.0 Resultados", 2, 2),
              Block("heading", "40 larvas / muestreo", 2, 2),
              Block("heading", "ANEXO A", 3, 1), Block("heading", "1.0 Cálculo", 3, 2)]
    out = run("sections", run("outline", doc(blocks, title="otro")))
    assert out.blocks[2].kind == "paragraph"
    last = out.blocks[-1]
    assert last.level == 1 and last.meta["scope"] == "ANEXO A"
    assert last.section == ("ANEXO A", "1.0 Cálculo")


def test_sections_paths_and_rules_drop_sections():
    blocks = [Block("heading", "Manual", 1, 0, meta={"title": True}), Block("heading", "1. Plagas", 1, 1),
              Block("heading", "1.1 Botrytis", 1, 2), Block("paragraph", "Moho gris.", 1),
              Block("heading", "Referencias bibliográficas", 2, 1), Block("paragraph", "Kogan 1998.", 2)]
    out = run("sections", doc(blocks))
    assert out.blocks[3].section == ("1. Plagas", "1.1 Botrytis")
    kept = run("rules", out, drop_sections=["referencias"])
    assert [b.text for b in kept.blocks][-1] == "Moho gris."
    assert kept.meta["dropped"][0]["reason"].startswith("sección excluida")
