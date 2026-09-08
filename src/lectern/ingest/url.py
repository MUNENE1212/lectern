"""Fetch a web article and keep the prose, dropping navigation and boilerplate."""

from __future__ import annotations

import hashlib
import re

from . import Document

_DROP = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"}


def load(target: str) -> Document:
    import httpx
    from bs4 import BeautifulSoup

    resp = httpx.get(
        target,
        follow_redirects=True,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Lectern/0.1)"},
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup.find_all(list(_DROP)):
        tag.decompose()

    title = (soup.title.get_text(strip=True) if soup.title else "") or target
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = main.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return Document(
        title=title,
        pages=[text],
        fmt="url",
        source_path=None,
        source_hash=hashlib.sha256(target.encode()).hexdigest(),
        notes=[f"fetched from {target}"],
    )
