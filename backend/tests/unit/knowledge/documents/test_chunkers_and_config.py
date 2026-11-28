"""Chunkers, the contextual header, the mixed-route merge and the configuration (registries, overrides, signature)."""
import pytest

from knowledge.documents.chunkers import add_headers
from knowledge.documents.config import load_config
from knowledge.documents.model import Block, Cell, NormalizedDocument
from knowledge.documents.registry import CHUNKERS
from knowledge.documents.routes import merge_mixed
from knowledge.documents.tokens import ApproxTokens

TOK = ApproxTokens()
SENT = "El fungicida se aplica cada siete días durante la floración del arándano. "


def doc(blocks, title="Manual"):
    return NormalizedDocument(doc_id="d1", title=title, source_format="pdf", blocks=tuple(blocks), pages=3)


def chunker(name, **opts):
    return CHUNKERS.create(name, tokens=TOK, language="es", **opts)


def sectioned():
    a, b = ("1. Plagas", "1.1 Botrytis"), ("1. Plagas", "1.2 Mosca")
    table = Block("table", "", 2, cells=(Cell("Producto", 1, 1, header=True), Cell("Carencia", 1, 2, header=True),
                                         Cell("ALINA", 2, 1), Cell("30", 2, 2)), section=b)
    return doc([Block("heading", "1.1 Botrytis", 1, 2, section=a), Block("paragraph", SENT * 3, 1, section=a),
                Block("paragraph", SENT * 40, 1, section=a), Block("heading", "1.2 Mosca", 2, 2, section=b),
                Block("caption", "Tabla 1. Productos", 2, section=b), table, Block("paragraph", "Corto.", 3, section=b)])


def test_structural_never_crosses_sections_keeps_tables_whole_and_cuts_between_sentences():
    chunks = chunker("structural", max_tokens=120, min_tokens=20)(sectioned())
    assert all(len(set(c.section)) and c.section in {("1. Plagas", "1.1 Botrytis"), ("1. Plagas", "1.2 Mosca")} for c in chunks)
    tables = [c for c in chunks if "table" in c.kinds]
    assert len(tables) == 1 and tables[0].text.startswith("Tabla 1. Productos\n\n| Producto | Carencia |")
    long_ = [c for c in chunks if c.section[-1] == "1.1 Botrytis"]
    assert len(long_) > 2 and all(c.tokens <= 120 for c in long_)
    assert all(c.text.rstrip().endswith(".") for c in long_)          # every piece ends at a sentence boundary


def test_fixed_respects_budget_and_overlaps():
    chunks = chunker("fixed", max_tokens=60, overlap_tokens=15)(sectioned())
    assert all(c.tokens <= 60 for c in chunks)
    first, second = chunks[0].text.split(), chunks[1].text.split()
    tail = " ".join(first[-15:])
    assert " ".join(second[:5]) in tail                              # the next chunk starts inside the previous one


def test_page_chunker_groups_by_page():
    chunks = chunker("page", max_tokens=5000)(sectioned())
    assert [c.pages for c in chunks] == [(1,), (2,), (3,)]


def test_parent_child_collapses_single_child_and_links_children():
    chunks = chunker("parent_child", max_tokens=400, min_tokens=20, child_tokens=60)(sectioned())
    roles = [c.meta["role"] for c in chunks]
    assert "parent" in roles and "child" in roles and "atomic" in roles
    parents = {c.chunk_id for c in chunks if c.meta["role"] == "parent"}
    assert all(c.meta["parent_id"] in parents for c in chunks if c.meta["role"] == "child")
    assert all(c.meta["role"] == "atomic" for c in chunks if "table" in c.kinds)


def test_header_goes_to_embedding_text_not_to_stored_text():
    d = sectioned()
    c = add_headers(d, chunker("structural")(d))[0]
    assert c.header == "Documento: Manual\nSección: 1. Plagas > 1.1 Botrytis"
    assert not c.text.startswith("Documento") and c.embedding_text.startswith(c.header + "\n\n")


def test_mixed_takes_tables_from_structured_and_text_from_markdown():
    md_table = Block("table", "", 2, cells=(Cell("a", 1, 1), Cell("b", 1, 2), Cell("", 2, 1), Cell("x", 2, 2)))
    md = doc([Block("paragraph", "texto markdown", 2), md_table, Block("paragraph", "después", 2)])
    st_table = Block("table", "", 2, cells=(Cell("a", 1, 1), Cell("b", 1, 2), Cell("x", 2, 2, row_span=2)))
    extra = Block("table", "", 3, cells=(Cell("solo estructurada", 1, 1), Cell("y", 1, 2)))
    st = doc([Block("paragraph", "texto estructurado", 2), st_table, Block("paragraph", "fin", 3), extra])
    out = merge_mixed(md, st).blocks
    assert out[0].text == "texto markdown" and out[1] is st_table and out[2].text == "después"
    assert out[-1] is extra


def test_config_overrides_env_validation_and_signature(monkeypatch):
    base = load_config(env=False)
    # the default chunker is the one frozen in stage 3 (V7, 24/11/2026)
    assert base.route == "markdown" and base.extractors["pdf"] == "opendataloader" and base.chunker.name == "parent_child"
    monkeypatch.setenv("DOCS_ROUTE", "structured")
    monkeypatch.setenv("DOCS_CHUNKER", "fixed")
    monkeypatch.setenv("DOCS_CONTEXTUAL_HEADER", "off")
    env = load_config()
    assert (env.route, env.chunker.name, env.contextual_header) == ("structured", "fixed", False)
    assert env.signature() != base.signature()
    assert load_config(env=False, pdf="pymupdf", max_tokens=300).chunker.max_tokens == 300
    with pytest.raises(ValueError, match="extractor desconocido"):
        load_config(env=False, pdf="no_existe")
    with pytest.raises(ValueError, match="no lee .pdf"):
        load_config(env=False, pdf="docx")


# --- stage 3 variants (V2, V3, V4, V6) ---------------------------------------------------------------------------------

def test_variant_options_off_keep_the_old_signature_and_on_change_it():
    base = load_config(env=False)
    assert base.with_overrides(merge_section_tokens=None).signature() == base.signature()
    for change in ({"merge_section_tokens": 120}, {"generic_sections": "drop"}, {"table_rows": True}, {"header": "short"}):
        assert base.with_overrides(**change).signature() != base.signature()


def test_v2_small_sections_join_the_next_of_the_same_parent():
    p = "1. Plagas"
    blocks = [Block("paragraph", "Breve.", 1, section=(p, "1.1 A")), Block("paragraph", "Otra breve.", 1, section=(p, "1.2 B")),
              Block("paragraph", "Distinto padre.", 2, section=("2. Riego", "2.1 C"))]
    off = chunker("structural", max_tokens=200, min_tokens=5)(doc(blocks))
    on = chunker("structural", max_tokens=200, min_tokens=5, merge_section_tokens=120)(doc(blocks))
    assert len(off) == 3 and len(on) == 2
    assert on[0].text == "Breve.\n\nOtra breve." and on[1].section == ("2. Riego", "2.1 C")   # never across parents


def test_v3_short_header_keeps_title_and_last_two_levels():
    d = doc([Block("paragraph", "Texto.", 1, section=("1. A", "1.1 B", "1.1.1 C"))], title="Manual de palto")
    full = add_headers(d, chunker("structural")(d))[0].header
    short = add_headers(d, chunker("structural")(d), "short")[0].header
    assert full.endswith("1. A > 1.1 B > 1.1.1 C") and short == "Documento: Manual de palto\nSección: 1.1 B > 1.1.1 C"


def test_v4_drop_generic_sections():
    blocks = [Block("paragraph", "Este trabajo resume…", 1, section=("Resumen",)),
              Block("paragraph", "Se concluye que…", 9, section=("5. Conclusiones",)),
              Block("paragraph", "Aplicar azoxistrobina cada 14 días.", 4, section=("3. Manejo de oídio",))]
    kept = chunker("structural", generic_sections="drop")(doc(blocks))
    assert [c.section for c in kept] == [("3. Manejo de oídio",)]


def test_v6_large_table_splits_by_rows_repeating_the_header():
    cells = [Cell("Producto", 1, 1, header=True), Cell("Carencia (días)", 1, 2, header=True)]
    cells += [x for r in range(2, 42) for x in (Cell(f"Producto comercial número {r}", r, 1), Cell(str(r), r, 2))]
    d = doc([Block("table", "", 2, cells=tuple(cells), section=("Tabla",))])
    whole = chunker("structural", max_tokens=120)(d)
    split = chunker("structural", max_tokens=120, table_rows=True)(d)
    assert len(whole) == 1 and len(split) > 2
    assert all(c.text.startswith("| Producto | Carencia (días) |") for c in split)        # every group keeps the header
    body = [ln for c in split for ln in c.text.splitlines()[2:]]
    assert len(body) == 40                                                                 # no row lost or repeated


# --- V6b: tables as sentences for the encoder ------------------------------------------------------------------------

def test_v6b_table_sentences_one_per_row_keeping_the_caption():
    from knowledge.documents.chunkers.structural import table_sentences
    md = "Tabla 2. Carencias\n\n| Producto | Cultivo | Carencia (días) |\n|---|---|---|\n| ALINA | palto | 30 |\n| SCORE | | 14 |"
    assert table_sentences(md) == ("Tabla 2. Carencias\nProducto: ALINA; Cultivo: palto; Carencia (días): 30.\n"
                                   "Producto: SCORE; Carencia (días): 14.")                          # empty cells left out


def test_v6b_only_tables_get_vector_text_and_the_user_still_sees_the_table():
    plain = chunker("structural", max_tokens=200)(sectioned())
    chunks = chunker("structural", max_tokens=200, table_text="filas")(sectioned())
    table = next(c for c in chunks if "table" in c.kinds)
    assert table.text == next(c for c in plain if "table" in c.kinds).text                  # what is shown is unchanged
    assert "Producto: ALINA; Carencia: 30." in table.vector_text
    assert "Producto: ALINA; Carencia: 30." in add_headers(sectioned(), [table])[0].embedding_text
    assert all(not c.vector_text for c in chunks if "table" not in c.kinds)
    base = load_config(env=False)
    assert base.with_overrides(table_text="filas").signature() != base.signature()


def test_v6b_works_on_tables_split_by_rows():
    cells = [Cell("Producto", 1, 1, header=True), Cell("Dosis", 1, 2, header=True)]
    cells += [x for r in range(2, 42) for x in (Cell(f"Producto comercial número {r}", r, 1), Cell(f"{r} ml/L", r, 2))]
    d = doc([Block("table", "", 2, cells=tuple(cells), section=("Tabla",))])
    split = chunker("structural", max_tokens=120, table_rows=True, table_text="filas")(d)
    assert len(split) > 2 and all(c.vector_text.startswith("Producto: Producto comercial") for c in split)
    assert sum(c.vector_text.count("Dosis:") for c in split) == 40


def test_v6b_wrapped_pdf_table_is_written_by_column_and_the_header_is_rejoined():
    from knowledge.documents.chunkers.structural import table_sentences
    md = ("| INGREDIENTE | CULTIVO | PLAGA | DOSIS |\n|---|---|---|---|\n| ACTIVO |  |  |  |\n"
          "| Trichoderma | Palto, | Rhizoctonia solani; | De acuerdo |\n| viride | Algodón, | Sclerotinia | a su uso |\n"
          "|  | Flores | sclerotiorum |  |")
    assert table_sentences(md) == ("INGREDIENTE ACTIVO: Trichoderma viride; CULTIVO: Palto, Algodón, Flores; "
                                   "PLAGA: Rhizoctonia solani; Sclerotinia sclerotiorum; DOSIS: De acuerdo a su uso.")
