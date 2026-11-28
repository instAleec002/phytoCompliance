"""Real spray programs through the exact core (review of the short paper, 26/11/2026).

The resolver moved to the system on 27/11/2026 (``knowledge.programs.resolver``, stage E), so that a field sheet is
imported by the same code that was measured here; this module keeps the old import path for the evaluation commands.
"""
from knowledge.programs.resolver import ETAPAS, LEXICO, MESES, NO_PLAGUICIDA, Fila, Resolvedor, _fonetico, _plano

__all__ = ["ETAPAS", "LEXICO", "MESES", "NO_PLAGUICIDA", "Fila", "Resolvedor", "_fonetico", "_plano"]
