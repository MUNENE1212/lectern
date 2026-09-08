# Lectern

Turn readings into navigable audio, and study alongside them.

Built after converting a 417-page textbook to audio by hand and hitting every trap on the
way. Phase 1 (this release) covers ingest → chapter detection → audiobook → web library.

## Why it is not a shell script

A naive "PDF → text-to-speech" pipeline produces confidently wrong audio:

| Trap | What Lectern does |
|---|---|
| Many PDFs encode `fi`/`ff`/`fl` ligatures in the Unicode **Private Use Area**. Poppler drops them silently — `find` becomes `nd`, `efficient` becomes `ecient`. One real textbook had **3,214** corrupted words. | Extracts with PyMuPDF, which preserves the codepoints, then **infers** each mapping by testing candidate expansions against a dictionary. Asserts zero residual. |
| Chapter structure is often missing — no embedded outline at all. | A cascade: outline → the book's own table of contents → running headers → heading regex → fixed chunks, each reporting its confidence. |
| Printed page numbers rarely match PDF page numbers. | Solves the offset from page furniture and corroborates it across widely-spaced pages before trusting it. |
| A wrong chapter split wastes hours of synthesis. | Proposes the structure and **waits for confirmation** before rendering. |
| Rendering a book takes hours. | Parallel workers sized to free memory, and fully resumable. |

## Install

```bash
python3 -m venv ~/.local/share/lectern/venv
~/.local/share/lectern/venv/bin/pip install -e .
ln -sf ~/.local/share/lectern/venv/bin/lectern ~/.local/bin/lectern
```

Needs `ffmpeg`, and a [piper voice](https://huggingface.co/rhasspy/piper-voices) in
`~/.local/share/piper-voices/`. Calibre is optional, for EPUB/MOBI/DOCX input.

## Use

```bash
lectern add "Textbook.pdf"          # ingest; proposes chapters, asks before committing
lectern add https://example.com/article
lectern chapters my-book --keep 1-12   # drop appendices
lectern render my-book                 # MP3s per chapter + a chaptered M4B
lectern serve                          # web library at localhost:8765
lectern find "naming convention"       # full-text search, with chapter and page
lectern list
lectern inbox                          # file everything dropped in ~/Lectern Inbox
lectern doctor                         # audit the naming protocol
```

## Managing resources

The storage layer follows the principles the source textbook teaches: a consistent naming
protocol, nothing left loose, every source retrievable.

**Naming.** All paths come from `lectern.naming`; nothing builds a filename ad hoc.
Inside a book folder, names are player-friendly and sort correctly (`07 - Thinking.mp3`).
Anything that can leave its folder is self-describing, so it is still identifiable months
later — the "78 documents called `Notes`" failure:

```
college-success--ch07--2026-09-08--managing-resources.md
```

**No clutter.** Drop files in `~/Lectern Inbox`; `lectern inbox` files them and leaves it
empty. Duplicates are rejected by content hash. `lectern doctor` audits for violations.

**Retrieval by content.** SQLite FTS5 over every chapter, so you search for what something
said rather than what you named it.

## Configuration

`~/.config/lectern/config.toml` (all optional):

```toml
[library]
root  = "~/.local/share/lectern/library"   # point at a roomier volume if you have one
inbox = "~/Lectern Inbox"

[tts]
voice   = "en_US-lessac-medium"
workers = 3

[ai]                      # phases 2-4
default = "claude"
[ai.providers.claude]
kind = "cli"              # uses the authenticated `claude` CLI; no API key
[ai.providers.ollama]
kind = "openai"           # any OpenAI-compatible endpoint: Ollama, GLM, MiniMax, ...
base_url = "http://localhost:11434/v1"
model = "qwen2.5:3b"
```

API keys are referenced by environment-variable *name* (`api_key_env`), never stored here.

## Roadmap

Phase 1 (done): ingest, glyph repair, chapter detection, audio, naming, search, web library.
Phase 2: notes and highlights, source manager with APA/MLA/BibTeX export, session tracking.
Phase 3: chapter summaries, quizzes, Q&A grounded in the text with chapter/page citations.
Phase 4: spaced-repetition flashcards driven by recorded gaps; reminders.

## Development

```bash
~/.local/share/lectern/venv/bin/python -m pytest
```

Note: the repository lives on an NTFS volume, so the executable bit is not preserved.
Entry points are console scripts; nothing relies on `chmod +x`.

## License

MIT — see [LICENSE](LICENSE).

Built with [piper](https://github.com/rhasspy/piper) for speech, [PyMuPDF](https://pymupdf.readthedocs.io/)
for extraction, and [calibre](https://calibre-ebook.com/) for ebook formats.
