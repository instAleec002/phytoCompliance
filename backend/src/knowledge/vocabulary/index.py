"""The vocabulary index built from the latest AGROVOC snapshot and the graph: every label (normalized) points to the
graph term it names, and every term has its synonyms.

Labels come from three places: the AGROVOC concept linked to the term (preferred and alternative labels in Spanish,
English and Latin), the SIGIA common names of each pest (e.g. «Oidiosis» for Erysiphe necator), and the Spanish names
of the ingredients (aliases and config/ingredient_nombres_es.yaml). ``expand`` gives, for a question, the synonyms of
every term it mentions, which the lexical retrieval adds to its query."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .agrovoc import norm

CROP_ES = {"blueberry": ["arándano", "arándanos"], "avocado": ["palto", "palta", "paltas", "aguacate"],
           "table_grape": ["uva de mesa", "vid", "uva", "viñedo"]}


@dataclass
class Term:
    kind: str
    key: str
    labels: set[str] = field(default_factory=set)          # display forms, any language
    uri: str | None = None


@dataclass
class Vocabulary:
    terms: dict[tuple[str, str], Term]
    by_label: dict[str, list[tuple[str, str]]]      # one label can name several terms («Oidiosis»)

    @classmethod
    def build(cls, agrovoc_folder: Path | None, pests: list[tuple[str, str, str]], ingredient_es: dict[str, str]) -> Vocabulary:
        """``pests``: (key, scientific name, SIGIA common name); ``ingredient_es``: ISO -> Spanish name."""
        terms: dict[tuple[str, str], Term] = {}

        def term(kind, key) -> Term:
            return terms.setdefault((kind, key), Term(kind, key))

        for crop, names in CROP_ES.items():
            term("crop", crop).labels.update(names)
        for key, sci, common in pests:
            t = term("pest", key)
            t.labels.update(x.strip() for x in (sci, common) if x and x.strip())
        for iso, es in ingredient_es.items():
            term("ingredient", iso).labels.update({iso, es})
        if agrovoc_folder and (agrovoc_folder / "enlaces.json").exists():
            concepts = json.loads((agrovoc_folder / "conceptos.json").read_text(encoding="utf-8"))
            for link in json.loads((agrovoc_folder / "enlaces.json").read_text(encoding="utf-8")):
                c = concepts.get(link.get("uri") or "")
                if not c:
                    continue
                t = term(link["kind"], link["key"])
                t.uri = c["uri"]
                for group in (c.get("pref", {}), c.get("alt", {})):
                    for vals in group.values():
                        t.labels.update(vals)
        by_label: dict[str, list[tuple[str, str]]] = {}
        for k, t in terms.items():
            for lab in t.labels:
                n = norm(lab)
                if len(n) >= 4 and k not in by_label.setdefault(n, []):   # short labels only through CROP_ES
                    by_label[n].append(k)
        for crop, names in CROP_ES.items():
            for n in names:
                if ("crop", crop) not in by_label.setdefault(norm(n), []):
                    by_label[norm(n)].append(("crop", crop))
        return cls(terms, by_label)

    def find(self, text: str) -> list[Term]:
        """Terms whose label appears in ``text`` as whole words, longest labels first (no overlapping matches)."""
        t = f" {norm(text)} "
        found, taken = [], []
        for lab in sorted(self.by_label, key=len, reverse=True):
            i = t.find(f" {lab} ")
            if i < 0 or any(a <= i < b for a, b in taken):
                continue
            taken.append((i, i + len(lab) + 2))
            for key in self.by_label[lab]:
                term = self.terms[key]
                if term not in found:
                    found.append(term)
        return found

    def mentions(self, text: str) -> set[tuple[str, str]]:
        """(kind, key) of every term named in ``text``, for whole fragments (D4, 27/11/2026): the words of the text are
        read left to right and, at each word, the longest label that starts there is taken (no overlaps). Same labels
        and normalization as ``find``, in time linear in the text instead of in the number of labels."""
        largo = self.__dict__.get("_max_words")
        if largo is None:
            largo = self.__dict__["_max_words"] = max((len(lab.split()) for lab in self.by_label), default=1)
        words = norm(text).split()
        out: set[tuple[str, str]] = set()
        i = 0
        while i < len(words):
            for n in range(min(largo, len(words) - i), 0, -1):
                keys = self.by_label.get(" ".join(words[i:i + n]))
                if keys:
                    out.update(keys)
                    i += n
                    break
            else:
                i += 1
        return out

    def expand(self, text: str, max_per_term: int = 6) -> list[str]:
        """Synonyms of the terms mentioned in ``text`` that the text does not already contain."""
        t = norm(text)
        out: list[str] = []
        for term in self.find(text):
            extra = sorted((x for x in term.labels if norm(x) not in t), key=len)[:max_per_term]
            out += extra
        return out

    def pairs(self, max_per_term: int = 6) -> list[dict]:
        """Synonym pairs for the encoder's LoRA (stage 9): two labels of the same term as anchor and positive.

        Labels that name more than one term («Oidiosis» for several fungi) are left out, since they would teach a
        false equivalence; labels equal after normalizing count once; each term gives at most ``max_per_term`` pairs
        so terms with many names do not dominate. The order is deterministic (shortest labels first)."""
        from itertools import combinations

        out = []
        for (kind, key), t in sorted(self.terms.items()):
            seen, labels = set(), []
            for lab in sorted(t.labels, key=lambda x: (len(x), x)):
                n = norm(lab)
                if len(n) < 4 or n in seen or len(self.by_label.get(n, [])) > 1:
                    continue
                seen.add(n)
                labels.append(lab.strip())
            for a, b in list(combinations(labels, 2))[:max_per_term]:
                out.append({"anchor": a, "positive": b, "kind": kind, "key": key})
        return out

    def stats(self) -> dict:
        kinds = {}
        for (kind, _), t in self.terms.items():
            k = kinds.setdefault(kind, {"terminos": 0, "con_agrovoc": 0, "etiquetas": 0})
            k["terminos"] += 1
            k["con_agrovoc"] += bool(t.uri)
            k["etiquetas"] += len(t.labels)
        return kinds


_WORD = re.compile(r"\w+")
