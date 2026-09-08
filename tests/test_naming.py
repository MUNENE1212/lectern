from pathlib import Path

from lectern import naming


def test_slug_is_lowercase_kebab():
    assert naming.slugify("College Success — A Student's Guide!") == "college-success-a-student-s-guide"
    assert naming.slugify("  ") == "untitled"


def test_slug_is_case_folded():
    # The library lives on a case-insensitive filesystem, so Notes and notes must
    # never produce two different slugs.
    assert naming.slugify("Notes") == naming.slugify("NOTES") == "notes"


def test_chapter_stem_zero_pads_so_players_sort_correctly():
    stems = [naming.chapter_stem(i, f"Chapter {i}") for i in (2, 10)]
    assert stems == ["02 - Chapter 2", "10 - Chapter 10"]
    assert sorted(stems) == stems


def test_chapter_stem_strips_filesystem_hostile_characters():
    assert "/" not in naming.chapter_stem(1, "Reading / Note-Taking")
    assert ":" not in naming.chapter_stem(1, "Thinking: A Primer")


def test_portable_name_is_self_describing():
    import datetime

    name = naming.portable_name(
        "College Success", "ch07", "Managing Resources", "md",
        date=datetime.date(2026, 9, 8),
    )
    assert name == "college-success--ch07--2026-09-08--managing-resources.md"
    assert naming.violations(Path(name)) == []


def test_ambiguous_names_are_violations():
    # The "78 documents called Notes" failure the book warns about.
    assert naming.violations(Path("Notes.md"))
    assert naming.violations(Path("untitled.txt"))


def test_paths_all_come_from_naming(tmp_path):
    p = naming.chapter_audio_path(tmp_path, "college-success", 7, "Thinking")
    assert p.name == "07 - Thinking.mp3"
    assert p.parent.name == "audio"
