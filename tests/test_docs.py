"""Guard against documentation rot: every relative link must resolve."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)#]+?)(#[^)]*)?\)")
EXTERNAL = ("http://", "https://", "mailto:")


def test_relative_markdown_links_resolve():
    broken = []
    for md in ROOT.rglob("*.md"):
        if ".git" in md.parts:
            continue
        text = md.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            target = match.group(1).strip()
            if not target or target.startswith(EXTERNAL) or target.startswith("/"):
                continue
            if not (md.parent / target).exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target}")
    assert not broken, "broken relative links: " + "; ".join(broken)
