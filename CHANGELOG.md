# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] — 2026-09-09

First release. Covers ingest through audiobook and a local web library.

### Added

- **Ingest** for PDF (PyMuPDF), EPUB/MOBI/AZW3/DOCX (calibre), URLs and plain text,
  keeping text page-by-page so citations can name an exact printed page.
- **Ligature repair** for PDFs that encode `fi`/`ff`/`fl`/`ffi`/`ffl` in the Unicode
  Private Use Area, where poppler silently drops them. Mappings are *inferred* by scoring
  candidate expansions against the system dictionary, not hardcoded; the repair asserts
  zero residual PUA characters and refuses to guess without evidence.
- **Chapter detection cascade** — embedded outline, the book's own table of contents,
  running page headers, heading regex, then fixed chunks — each reporting its source and
  confidence. TOC parsing uses a longest-increasing-subsequence over page numbers so
  front-matter noise cannot displace the real chapter spine.
- **Printed-page offset solver**, corroborated across widely-spaced pages before use.
- **Confirmation gate**: the proposed structure is shown and approved before rendering.
- **Rendering** via piper, parallelised to free memory as well as cores, and resumable.
- **Output** as tagged per-chapter MP3s and a single M4B with embedded chapter markers.
- **Naming protocol** enforced in `lectern.naming`; nothing constructs a filename ad hoc.
- **Library**: inbox intake, content-hash dedupe, SQLite FTS5 search, `lectern doctor`.
- **Web library** with progress, chapter jump, resume position and HTTP Range seeking.

[Unreleased]: https://github.com/MUNENE1212/lectern/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MUNENE1212/lectern/releases/tag/v0.1.0
