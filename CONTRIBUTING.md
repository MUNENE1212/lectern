# Contributing

Thanks for taking a look. Bug reports about *specific documents that convert badly* are
especially useful — this problem space is mostly edge cases.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

You will also need `ffmpeg`, and a [piper voice](https://huggingface.co/rhasspy/piper-voices)
in `~/.local/share/piper-voices/` if you want to render audio. Calibre is optional, for
EPUB/MOBI/DOCX input.

## Before opening a pull request

```bash
ruff check src tests
ruff format src tests
pytest
```

CI runs exactly these on Python 3.11 and 3.12.

## What good looks like here

**Never guess at text.** The repair stage exists because a plausible-looking wrong word is
worse than a visibly broken one — it gets read aloud with total confidence. If a
transformation cannot be justified from evidence in the document, leave the text alone and
report it as unresolved.

**Detection is a proposal, not a fact.** Anything that infers structure should report which
source it used and how confident it is, and let the user confirm. Rendering is measured in
hours; a silent wrong guess is expensive.

**All paths come from `lectern.naming`.** No module builds a filename by hand. If you need
a new kind of file, add it there.

**Prefer evidence to hardcoding.** The ligature mapping is inferred by scoring candidates
against a dictionary rather than shipping a lookup table, because the next PDF will use
different codepoints. Solve the class of problem where you reasonably can.

## Tests

Unit tests must not need network access, a GPU, or the multi-gigabyte model files. Anything
requiring a real PDF fixture should skip cleanly when it is absent.

## Reporting a conversion bug

Please include the tool's own diagnosis, which is usually enough to pinpoint the stage:

```bash
lectern add "the-problem.pdf"   # copy the glyph report and structure table
```

Say what you expected the chapters to be, and — if you can share it — where the document
came from. Do not attach copyrighted books.
