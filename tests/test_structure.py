from lectern.structure import detect


def _paged(printed_start: int, n: int, offset: int) -> list[str]:
    """Build pages whose headers carry printed numbers with a known offset."""
    pages = ["front matter"] * offset
    for i in range(n):
        pages.append(f"{printed_start + i}\nbody text for page {printed_start + i}\n")
    return pages


def test_offset_solver_recovers_a_known_offset():
    pages = _paged(1, 60, 10)
    offset, conf = detect.solve_offset(pages)
    assert offset == 10
    assert conf > 0.5


def test_offset_solver_declines_without_corroboration():
    # Two stray numbers are not evidence of a page-numbering scheme.
    offset, conf = detect.solve_offset(["7", "nothing here", "also nothing"])
    assert offset is None


def test_longest_increasing_discards_leading_outlier():
    # A copyright page contributes ("PUBLICATION YEAR", 2020) before the real spine;
    # a naive left-to-right scan would discard every genuine chapter after it.
    pairs = [("Publication Year", 2020), ("One", 7), ("Two", 31), ("Three", 65)]
    kept = detect._longest_increasing(pairs)
    assert [t for t, _ in kept] == ["One", "Two", "Three"]


def test_implausible_titles_rejected():
    assert not detect._plausible_title("3 4 5 6 7 8 9 10 CJP 26 23")
    assert not detect._plausible_title("978-1-951693-18-3")
    assert detect._plausible_title("Exploring College")
    assert detect._plausible_title("Thinking")


def test_single_page_input_is_not_split():
    s = detect.detect(["just one article of prose"])
    assert s.source == "single"
    assert len(s.chapters) == 1


def test_falls_back_to_chunks_when_nothing_is_detectable():
    s = detect.detect(["lorem ipsum"] * 80)
    assert s.source == "chunks"
    assert len(s.chapters) > 1
