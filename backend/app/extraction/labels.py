"""Option-label normalisation shared by extraction, answer keys and validation.

Papers label options as (a), A., a), (1), 1., (i), [A], "Option C"... Everything is mapped to A, B, C...
before answers are matched, so an answer key that says "(3)" or "iii" lines up with option C.
"""

import re

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8}
_LETTERS = "ABCDEFGH"


def clean_label(raw: str) -> str:
    """'(a)' -> 'A', ' Option c. ' -> 'C', '(3)' -> '3', '(iii)' -> 'C'. Unknown shapes are upper-cased."""
    s = re.sub(r"(?i)^\s*option\s*", "", raw or "").strip().strip("()[]{}.:- ").strip()
    if s.lower() in _ROMAN and s.lower() not in ("v",):  # "v" alone is more often a typo than option 5
        return _LETTERS[_ROMAN[s.lower()] - 1]
    if len(s) == 1 and s.isalpha():
        return s.upper()
    return s.upper()


def normalize_answer(raw: list[str], option_labels: list[str] | None = None) -> list[str]:
    """Normalise answer labels; numeric answers map to letters when the options are lettered."""
    labels = {clean_label(a) for a in raw if a and a.strip()}
    labels.discard("")
    lettered = option_labels is None or not any(label.isdigit() for label in option_labels)
    if lettered and labels and all(label.isdigit() and 1 <= int(label) <= len(_LETTERS) for label in labels):
        labels = {_LETTERS[int(label) - 1] for label in labels}
    return sorted(labels)
