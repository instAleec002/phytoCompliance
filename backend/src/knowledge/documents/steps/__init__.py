"""Steps after extraction. Importing the package registers them; the configuration chooses which run and in which
order (default: text, furniture, tables, outline, sections; ``rules`` when a source defines rules, before ``sections``
is not needed because rules read the paths that ``sections`` writes, so it goes after it)."""
from . import furniture, outline, rules, sections, tables, text  # noqa: F401  (registration)
from .base import Step, pages_of

__all__ = ["Step", "pages_of"]
