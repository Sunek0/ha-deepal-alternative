"""Tests that the published SDK documentation set is complete, fresh and secret-free.

The documentation set is the README plus every file under ``docs/``; the LLM files
(``llms.txt`` and ``llms-full.txt``) are generated from it by
``scripts/generate-llms-docs.py``. These tests are offline and self-contained so they also run in
the published mirror, where the private ``scripts/`` tree does not exist.
"""

from __future__ import annotations

import re
from pathlib import Path

SDK_ROOT = Path(__file__).resolve().parents[1]

MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{20,}")
HEX_TOKEN_RE = re.compile(r"\b[0-9a-f]{32,}\b")
PEM_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def published_documents() -> list[Path]:
    """Return every document the mirror publishes, README first."""
    return [SDK_ROOT / "README.md", *sorted((SDK_ROOT / "docs").rglob("*.md"))]


def relative_path(path: Path) -> str:
    return path.relative_to(SDK_ROOT).as_posix()


def index_targets() -> list[str]:
    """Return the markdown targets listed in ``llms.txt``."""
    text = (SDK_ROOT / "llms.txt").read_text(encoding="utf-8")
    targets = []
    for target in MARKDOWN_LINK_RE.findall(text):
        clean = target.split("#", 1)[0]
        if clean.endswith(".md"):
            targets.append(clean)
    return targets


def test_llms_files_exist_and_follow_the_index_shape() -> None:
    index = (SDK_ROOT / "llms.txt").read_text(encoding="utf-8")
    full = (SDK_ROOT / "llms-full.txt").read_text(encoding="utf-8")
    assert index.startswith("# ")
    assert "\n> " in index
    assert full.startswith("# ")
    assert "do not edit by hand" in full


def test_index_lists_every_published_document() -> None:
    expected = {relative_path(path) for path in published_documents()}
    assert set(index_targets()) == expected


def test_index_targets_resolve() -> None:
    for target in index_targets():
        assert (SDK_ROOT / target).is_file(), f"llms.txt lists a missing file: {target}"


def test_full_contains_every_document_verbatim() -> None:
    full = (SDK_ROOT / "llms-full.txt").read_text(encoding="utf-8")
    for path in published_documents():
        content = path.read_text(encoding="utf-8").strip()
        assert content in full, f"llms-full.txt is stale for {relative_path(path)}"


def test_internal_links_resolve() -> None:
    broken: list[str] = []
    for path in published_documents():
        for target in MARKDOWN_LINK_RE.findall(path.read_text(encoding="utf-8")):
            link = target.split("#", 1)[0].strip()
            if not link or link.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / link).resolve().exists():
                broken.append(f"{relative_path(path)} -> {target}")
    assert not broken, f"broken links: {broken}"


def test_documents_contain_no_real_looking_secrets() -> None:
    files = [
        *published_documents(),
        SDK_ROOT / "llms.txt",
        SDK_ROOT / "llms-full.txt",
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        name = relative_path(path)
        assert not PEM_RE.search(text), f"private key material in {name}"
        assert not JWT_RE.search(text), f"JWT-looking token in {name}"
        assert not HEX_TOKEN_RE.search(text), f"32+ hex character run in {name}"
        for email in EMAIL_RE.findall(text):
            assert email.endswith("@example.com"), f"real-looking email {email} in {name}"
