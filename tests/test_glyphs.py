"""The glyph repair must infer its mapping, never carry a hardcoded table."""

from lectern.repair import glyphs

FI, FF, FL, FFI, FFL = "", "", "", "", ""

WORDS = {"find", "first", "financial", "benefits", "effective", "different",
         "difficult", "office", "flexible", "offline", "reflection", "efficient"}


def _corpus() -> str:
    return " ".join([
        f"{FI}nd the {FI}rst {FI}nancial bene{FI}ts",
        f"e{FF}ective and di{FF}erent",
        f"{FL}exible re{FL}ection",
        f"di{FFI}cult o{FFI}ce e{FFI}cient",
        f"o{FFL}ine",
    ] * 6)


def test_infers_mapping_without_a_hardcoded_table():
    mapping, counts, unresolved = glyphs.infer_mapping(_corpus(), WORDS)
    assert mapping[FI] == "fi"
    assert mapping[FF] == "ff"
    assert mapping[FL] == "fl"
    assert mapping[FFI] == "ffi"
    assert mapping[FFL] == "ffl"
    assert not unresolved


def test_repair_leaves_no_private_use_characters():
    fixed, report = glyphs.repair(_corpus(), WORDS)
    assert report.residual == 0
    assert "find" in fixed and "difficult" in fixed and "offline" in fixed


def test_refuses_to_guess_when_evidence_is_absent():
    # A glyph appearing only in nonsense should stay unresolved rather than invent text.
    mapping, _, unresolved = glyphs.infer_mapping("xqzr " * 5, WORDS)
    assert "" not in mapping
    assert "" in unresolved


def test_clean_text_is_left_alone():
    text = "nothing to repair here"
    fixed, report = glyphs.repair(text, WORDS)
    assert fixed == text
    assert report.replaced == 0


def test_dehyphenate_joins_across_line_breaks():
    assert glyphs.dehyphenate("infor-\nmation") == "information"
