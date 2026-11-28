"""Entries of the mode-of-action classifications (FRAC fungicides, IRAC insecticides, HRAC herbicides)."""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

_CODE_SPACE = re.compile(r"^([A-Z]+)\s+(\d+)$")


def normalize_code(code: str) -> str:
    """'M 01' -> 'M01', 'BM 02' -> 'BM02', ' 11 ' -> '11'."""
    text = " ".join(str(code).split())
    m = _CODE_SPACE.match(text)
    return f"{m.group(1)}{m.group(2)}" if m else text


class MoaEntry(BaseModel):
    """One active ingredient (or biological agent) in one classification."""

    model_config = ConfigDict(frozen=True)

    scheme: str          # FRAC, IRAC or HRAC
    code: str            # normalized group code: "11", "M01", "4A", "UN"
    name: str            # as printed, one line
    group_name: str | None = None

    @property
    def group(self) -> str:
        return f"{self.scheme}:{self.code}"
