"""Per-source rules on blocks, so the same rule works for a PDF and a DOCX. Options (from ``step_options.rules`` in the
configuration, or from a source entry later):

- ``drop_sections``: regular expressions; every block whose section path contains a matching heading is dropped
  (a thesis's «Referencias bibliográficas», «Dedicatoria» or «Anexos»).
- ``drop_kinds``: block kinds to drop (for example ``["caption"]``).
- ``min_chars``: paragraphs shorter than this are dropped (default 0: keep everything)."""
from __future__ import annotations

import re

from ..model import NormalizedDocument
from ..registry import STEPS, register
from .base import Step, dropped


@register(STEPS, "rules")
class RulesStep(Step):
    name = "rules"

    def __call__(self, doc: NormalizedDocument) -> NormalizedDocument:
        patterns = [re.compile(p, re.IGNORECASE) for p in self.options.get("drop_sections", [])]
        kinds = set(self.options.get("drop_kinds", []))
        min_chars = int(self.options.get("min_chars", 0))
        kept, removed = [], []
        for b in doc.blocks:
            hit = next((p.pattern for p in patterns for s in b.section if p.search(s)), None)
            if hit:
                removed.append((b, f"sección excluida ({hit})"))
            elif b.kind in kinds:
                removed.append((b, f"tipo excluido ({b.kind})"))
            elif b.kind == "paragraph" and len(b.text) < min_chars:
                removed.append((b, f"párrafo de menos de {min_chars} caracteres"))
            else:
                kept.append(b)
        return doc.with_blocks(kept, **dropped(doc, self.name, removed))
