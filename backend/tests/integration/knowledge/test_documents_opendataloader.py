"""OpenDataLoader end to end on a PDF generated here (needs Java; skipped without it): the three routes produce
paged blocks, section paths from numbered headings, and chunks; several files go through one engine call."""
import shutil

import pymupdf
import pytest

from knowledge.documents import Pipeline, load_config

pytestmark = pytest.mark.skipif(shutil.which("java") is None, reason="OpenDataLoader necesita Java")


def make_pdf(path, chapters=("I.- Plagas", "II.- Control")):
    doc = pymupdf.open()
    for n, chapter in enumerate(chapters, start=1):
        page = doc.new_page()
        page.insert_text((72, 80), chapter, fontsize=20)
        page.insert_text((72, 120), f"{n}.1 Muestreo", fontsize=14)
        y = 150
        for k in range(8):
            page.insert_text((72, y), f"Se evaluan veinte plantas por sitio en el muestreo numero {k + 1}.", fontsize=11)
            y += 18
    doc.save(path)


@pytest.mark.parametrize("route", ["markdown", "structured", "mixed"])
def test_routes_give_paged_sectioned_chunks(tmp_path, route):
    pdf = tmp_path / "manual.pdf"
    make_pdf(pdf)
    result = Pipeline(load_config(env=False, route=route)).process(pdf, "manual")
    assert result.document.meta["engine"] == "opendataloader" and result.document.meta["route"] == route
    assert result.chunks and all(c.pages for c in result.chunks)
    sections = {c.section for c in result.chunks}
    assert any(s and s[-1].endswith("Muestreo") for s in sections)


def test_process_many_converts_in_one_call(tmp_path):
    a, b = tmp_path / "a.pdf", tmp_path / "b.pdf"
    make_pdf(a)
    make_pdf(b, chapters=("I.- Riego",))
    pipeline = Pipeline(load_config(env=False))
    results = pipeline.process_many([a, b])
    assert [r.path.name for r in results] == ["a.pdf", "b.pdf"] and all(r.chunks for r in results)
