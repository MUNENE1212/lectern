"""Repair text whose ligatures were encoded as Private Use Area codepoints.

Many PDFs subset their fonts so that ligature glyphs (fi, ff, fl, ffi, ffl) land in the
Unicode Private Use Area with no meaningful ToUnicode mapping. Poppler drops these
characters outright, which silently corrupts text -- "find" becomes "nd", "efficient"
becomes "ecient" -- and a text-to-speech pass will happily read the wreckage aloud.
PyMuPDF preserves the codepoints, so they can be recovered.

Rather than hardcode a table for one book, each PUA codepoint is *inferred*: for every
candidate expansion, substitute it everywhere the glyph appears and count how many of the
resulting words are real words. The expansion that produces the most real words wins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PUA = re.compile(r"[-\U000f0000-\U000ffffd]")
_WORD = re.compile(r"[A-Za-z-\U000f0000-\U000ffffd]{2,}")

# Ordered by prior likelihood; longer forms are tried too so "ffi" is reachable.
CANDIDATES = ("fi", "ff", "fl", "ffi", "ffl", "ft", "st", "tt", "ct", "sp", "Th")

DICT_PATHS = (
    Path("/usr/share/dict/american-english"),
    Path("/usr/share/dict/british-english"),
    Path("/usr/share/dict/words"),
)

# A mapping is only trusted if it turns most occurrences into real words and clearly
# beats the runner-up; otherwise we would silently invent text.
MIN_HIT_RATE = 0.55
MIN_MARGIN = 0.15


@dataclass
class GlyphReport:
    mapping: dict[str, str]
    counts: dict[str, int]
    unresolved: dict[str, int]
    residual: int
    replaced: int

    def summary(self) -> str:
        if not self.counts:
            return "no Private Use Area glyphs found"
        bits = ", ".join(
            f"U+{ord(g):04X}->{self.mapping.get(g, '?')} x{n}"
            for g, n in sorted(self.counts.items(), key=lambda kv: -kv[1])
        )
        out = f"repaired {self.replaced} glyphs ({bits})"
        if self.unresolved:
            out += f"; UNRESOLVED: {', '.join(f'U+{ord(g):04X}' for g in self.unresolved)}"
        return out


def load_dictionary() -> set[str]:
    words: set[str] = set()
    for p in DICT_PATHS:
        if p.is_file():
            with open(p, encoding="utf-8", errors="ignore") as fh:
                words.update(w.strip().lower() for w in fh if w.strip())
            break
    # Possessives and plurals of dictionary words appear constantly in prose.
    return words


def infer_mapping(text: str, words: set[str] | None = None) -> tuple[dict, dict, dict]:
    """Infer an expansion for every PUA codepoint present in ``text``."""
    words = load_dictionary() if words is None else words
    counts: dict[str, int] = {}
    for ch in PUA.findall(text):
        counts[ch] = counts.get(ch, 0) + 1
    if not counts:
        return {}, {}, {}

    # Collect the words each glyph appears in, keeping only those where it is the sole
    # unknown, so scoring is never confounded by a second unresolved glyph.
    samples: dict[str, list[str]] = {g: [] for g in counts}
    for match in _WORD.findall(text):
        present = set(PUA.findall(match))
        if len(present) == 1:
            g = present.pop()
            if len(samples[g]) < 400:
                samples[g].append(match)

    mapping: dict[str, str] = {}
    unresolved: dict[str, int] = {}
    for glyph, n in counts.items():
        pool = samples.get(glyph) or []
        if not pool:
            unresolved[glyph] = n
            continue
        scores: list[tuple[float, str]] = []
        for cand in CANDIDATES:
            hits = sum(
                1
                for w in pool
                if w.replace(glyph, cand).lower().strip("'’s") in words
                or w.replace(glyph, cand).lower() in words
            )
            scores.append((hits / len(pool), cand))
        scores.sort(reverse=True)
        best_rate, best = scores[0]
        runner = scores[1][0] if len(scores) > 1 else 0.0
        if best_rate >= MIN_HIT_RATE and (best_rate - runner) >= MIN_MARGIN:
            mapping[glyph] = best
        else:
            unresolved[glyph] = n
    return mapping, counts, unresolved


def repair(text: str, words: set[str] | None = None) -> tuple[str, GlyphReport]:
    """Return ``text`` with PUA ligatures expanded, plus a report of what was done."""
    mapping, counts, unresolved = infer_mapping(text, words)
    replaced = 0
    for glyph, expansion in mapping.items():
        replaced += text.count(glyph)
        text = text.replace(glyph, expansion)
    residual = len(PUA.findall(text))
    return text, GlyphReport(mapping, counts, unresolved, residual, replaced)


def dehyphenate(text: str) -> str:
    """Join words split across a line break by a hyphen ("infor-\\nmation")."""
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)


def non_dictionary_rate(text: str, words: set[str] | None = None) -> float:
    """Share of alphabetic tokens absent from the dictionary -- a corruption smell test."""
    words = load_dictionary() if words is None else words
    if not words:
        return 0.0
    toks = re.findall(r"\b[A-Za-z]{2,}\b", text)
    if not toks:
        return 0.0
    miss = sum(1 for t in toks if t.lower() not in words)
    return miss / len(toks)
