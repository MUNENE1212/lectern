"""Work out where the chapters are.

Sources are tried best-first. A real embedded outline is authoritative; failing that we
parse the book's own table of contents; failing that we fall back to the running headers
printed on each page, then to heading-shaped lines, then to fixed-size chunks.

Whatever is found is *proposed*, never assumed -- a wrong split costs an hour of
synthesis, so the caller confirms before rendering.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# Section headings that recur in every chapter of a textbook and must never be mistaken
# for chapter titles themselves.
BOILERPLATE = {
    "introduction",
    "summary",
    "rethinking",
    "career connection",
    "preface",
    "index",
    "where do you go from here?",
    "contents",
    "table of contents",
    "glossary",
    "references",
    "bibliography",
    "appendix",
    "acknowledgements",
    "acknowledgments",
}

_SECTION_NUM = re.compile(r"^\d{1,2}\.\d{1,2}\b")
_BARE_INT = re.compile(r"^\d{1,4}$")
_HEADER_RUN = re.compile(r"^\s*(\d{1,2})(?:\.\d{1,2})?\s*[•|]\s*(.+?)\s*$")


@dataclass
class Chapter:
    idx: int
    title: str
    page_start: int  # 1-based PDF page
    page_end: int  # inclusive
    word_count: int = 0

    @property
    def n_pages(self) -> int:
        return self.page_end - self.page_start + 1


@dataclass
class Structure:
    chapters: list[Chapter]
    source: str
    printed_offset: int | None = None
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------- printed page offset


def solve_offset(pages: list[str], min_agree: int = 3) -> tuple[int | None, float]:
    """Find ``pdf_page - printed_page``.

    Page numbers are printed in the header or footer, so the first and last few lines of
    each page are examined for a bare integer. The offset that the most pages agree on
    wins, and it must be corroborated by several widely-spaced pages before being trusted.
    """
    votes: Counter[int] = Counter()
    seen_pages: dict[int, list[int]] = {}
    for i, page in enumerate(pages, start=1):
        lines = [ln.strip() for ln in page.split("\n") if ln.strip()]
        for cand in lines[:3] + lines[-3:]:
            if _BARE_INT.match(cand):
                n = int(cand)
                if 0 < n <= len(pages) + 200:
                    off = i - n
                    if 0 <= off <= 100:
                        votes[off] += 1
                        seen_pages.setdefault(off, []).append(i)
    if not votes:
        return None, 0.0
    offset, hits = votes.most_common(1)[0]
    corroborating = seen_pages.get(offset, [])
    if len(corroborating) < min_agree or (max(corroborating) - min(corroborating)) < 10:
        return None, 0.0
    return offset, hits / max(1, sum(votes.values()))


# --------------------------------------------------------------------- source: outline


def from_outline(pdf_path: Path, n_pages: int) -> Structure | None:
    try:
        import pymupdf

        toc = pymupdf.open(pdf_path).get_toc()
    except Exception:
        return None
    tops = [(t.strip(), p) for lvl, t, p in toc if lvl == 1 and p > 0]
    if len(tops) < 2:
        return None
    chapters = []
    for i, (title, start) in enumerate(tops):
        end = (tops[i + 1][1] - 1) if i + 1 < len(tops) else n_pages
        chapters.append(Chapter(i + 1, title, start, max(start, end)))
    return Structure(chapters, "outline", None, 1.0, ["chapters from embedded PDF outline"])


# ------------------------------------------------------------------------ source: TOC


def _toc_pairs(pages: list[str], scan: int = 20) -> list[tuple[str, int]]:
    """Pull (title, printed page) pairs out of the front matter."""
    pairs: list[tuple[str, int]] = []
    for page in pages[:scan]:
        lines = [ln.strip() for ln in page.split("\n") if ln.strip()]
        for j, ln in enumerate(lines):
            # "Title .... 12" on one line
            m = re.match(r"^(.{3,90}?)\s*\.{2,}\s*(\d{1,4})$", ln)
            if m:
                pairs.append((m.group(1).strip(), int(m.group(2))))
                continue
            m = re.match(r"^(.{3,90}?)\s+(\d{1,4})$", ln)
            if m and not _BARE_INT.match(ln):
                pairs.append((m.group(1).strip(), int(m.group(2))))
                continue
            # Title on one line, page number alone on the next
            if (
                j + 1 < len(lines)
                and _BARE_INT.match(lines[j + 1])
                and not _BARE_INT.match(ln)
                and 3 <= len(ln) <= 90
            ):
                pairs.append((ln, int(lines[j + 1])))
    return pairs


def _plausible_title(title: str) -> bool:
    """Reject front-matter debris that happens to sit next to a number.

    Copyright pages yield lines like "3 4 5 6 7 8 9 10 CJP 26 23" and ISBN runs, which are
    shaped like a table-of-contents entry but are not titles. Real chapter titles are
    prose: mostly letters, with at least a couple of proper words.
    """
    t = title.strip()
    if not (4 <= len(t) <= 90):
        return False
    dense = [c for c in t if not c.isspace()]
    if not dense:
        return False
    if sum(c.isalpha() for c in dense) / len(dense) < 0.5:
        return False
    return sum(1 for w in re.findall(r"[A-Za-z]+", t) if len(w) >= 3) >= 1


def _longest_increasing(pairs: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Longest strictly increasing subsequence by page number, preserving order."""
    if not pairs:
        return []
    n = len(pairs)
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if pairs[j][1] < pairs[i][1] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
                prev[i] = j
    end = max(range(n), key=lambda i: best[i])
    out: list[tuple[str, int]] = []
    while end != -1:
        out.append(pairs[end])
        end = prev[end]
    return list(reversed(out))


def from_toc(pages: list[str], offset: int | None, n_pages: int) -> Structure | None:
    if offset is None:
        return None
    pairs = _toc_pairs(pages)
    if len(pairs) < 4:
        return None

    chapters_raw: list[tuple[str, int]] = []
    for title, printed in pairs:
        low = title.lower().strip(" .")
        if low in BOILERPLATE or _SECTION_NUM.match(title):
            continue
        if not _plausible_title(title):
            continue
        chapters_raw.append((title, printed))

    # Discard entries that could not correspond to a real page once the offset is
    # applied -- copyright pages contribute things like ("PUBLICATION YEAR", 2020).
    seen: set[str] = set()
    candidates: list[tuple[str, int]] = []
    for title, printed in chapters_raw:
        key = title.lower()
        if key in seen:
            continue
        if not (1 <= printed + offset <= n_pages):
            continue
        seen.add(key)
        candidates.append((title, printed))

    # Real chapter starts advance monotonically through the book, but the raw list is
    # peppered with noise from front matter and contributor pages. Taking the longest
    # strictly increasing subsequence keeps the true spine and drops outliers, which a
    # simple left-to-right scan cannot do -- one bad leading entry would eat the rest.
    ordered = _longest_increasing(candidates)
    if len(ordered) < 3:
        return None

    chapters = []
    for i, (title, printed) in enumerate(ordered):
        start = printed + offset
        end = (ordered[i + 1][1] + offset - 1) if i + 1 < len(ordered) else n_pages
        chapters.append(Chapter(i + 1, title, start, max(start, min(end, n_pages))))
    return Structure(
        chapters,
        "toc",
        offset,
        0.8,
        [f"chapters parsed from the book's table of contents (page offset +{offset})"],
    )


# -------------------------------------------------------------------- source: headers


def from_headers(pages: list[str], n_pages: int) -> Structure | None:
    """Use running headers like ``1 • Exploring College`` printed on each body page."""
    titles: dict[int, Counter] = {}
    first: dict[int, int] = {}
    for i, page in enumerate(pages, start=1):
        for ln in page.split("\n")[:6]:
            m = _HEADER_RUN.match(ln)
            if not m:
                continue
            num, title = int(m.group(1)), m.group(2).strip()
            if title.lower().strip(" .") in BOILERPLATE or len(title) < 4:
                continue
            titles.setdefault(num, Counter())[title] += 1
            first.setdefault(num, i)
    if len(titles) < 3:
        return None
    nums = sorted(titles)
    chapters = []
    for i, num in enumerate(nums):
        title = titles[num].most_common(1)[0][0]
        start = first[num]
        end = (first[nums[i + 1]] - 1) if i + 1 < len(nums) else n_pages
        chapters.append(Chapter(num, title, start, max(start, end)))
    return Structure(chapters, "headers", None, 0.5, ["chapters from running page headers"])


# ---------------------------------------------------------------------- source: regex


def from_regex(pages: list[str], n_pages: int) -> Structure | None:
    pat = re.compile(r"^\s*(?:CHAPTER|Chapter)\s+(\d{1,2})\b\s*[:.\-]?\s*(.*)$")
    hits: list[tuple[int, int, str]] = []
    for i, page in enumerate(pages, start=1):
        for ln in page.split("\n")[:12]:
            m = pat.match(ln.strip())
            if m:
                hits.append((i, int(m.group(1)), m.group(2).strip()))
                break
    if len(hits) < 3:
        return None
    chapters = []
    for k, (pg, num, title) in enumerate(hits):
        end = (hits[k + 1][0] - 1) if k + 1 < len(hits) else n_pages
        chapters.append(Chapter(num, title or f"Chapter {num}", pg, max(pg, end)))
    return Structure(chapters, "regex", None, 0.4, ["chapters from 'Chapter N' headings"])


# --------------------------------------------------------------------- source: chunks


def by_chunks(n_pages: int, size: int = 25) -> Structure:
    chapters = []
    for k, start in enumerate(range(1, n_pages + 1, size), start=1):
        end = min(start + size - 1, n_pages)
        chapters.append(Chapter(k, f"Part {k} (pages {start}-{end})", start, end))
    return Structure(
        chapters,
        "chunks",
        None,
        0.1,
        ["no structure detected -- split into fixed-size parts"],
    )


# ------------------------------------------------------------------------- the cascade


def detect(pages: list[str], pdf_path: Path | None = None) -> Structure:
    n = len(pages)
    if n == 0:
        return Structure([], "empty", None, 0.0, ["document is empty"])

    # A single-page document (article, URL, converted ebook) has no page structure.
    if n == 1:
        return Structure(
            [Chapter(1, "Full text", 1, 1, len(pages[0].split()))],
            "single",
            None,
            1.0,
            ["single-document input; no chapter split"],
        )

    offset, off_conf = solve_offset(pages)

    for candidate in (
        (from_outline(pdf_path, n) if pdf_path else None),
        from_toc(pages, offset, n),
        from_headers(pages, n),
        from_regex(pages, n),
    ):
        if candidate and len(candidate.chapters) >= 2:
            if candidate.printed_offset is None:
                candidate.printed_offset = offset
            if offset is not None:
                candidate.notes.append(
                    f"printed->PDF page offset +{offset} (agreement {off_conf:.0%})"
                )
            for ch in candidate.chapters:
                ch.word_count = sum(
                    len(pages[p - 1].split()) for p in range(ch.page_start, ch.page_end + 1)
                )
            return candidate

    s = by_chunks(n)
    for ch in s.chapters:
        ch.word_count = sum(
            len(pages[p - 1].split()) for p in range(ch.page_start, ch.page_end + 1)
        )
    return s
