from lectern import clean


def test_strips_page_furniture():
    raw = "\n".join([
        "20",
        "1 • Exploring College",
        "Real prose that must survive.",
        "Access for free at openstax.org",
        "Figure 1.1",
        "Credit: somebody",
        "•",
        "• A bulleted point",
        "See https://example.com/page for more",
    ])
    out = clean.for_tts(raw)
    assert "Real prose that must survive." in out
    assert "A bulleted point" in out
    for gone in ("20", "1 • Exploring College", "openstax.org", "Figure 1.1",
                 "Credit:", "https://"):
        assert gone not in out


def test_keeps_captioned_figures():
    out = clean.for_tts("Figure 5.1 Each of us reads in our own way.")
    assert "Each of us reads" in out


def test_chapter_text_announces_the_chapter():
    out = clean.chapter_text("Thinking", "Body.", idx=7)
    assert out.startswith("Chapter 7. Thinking.")
