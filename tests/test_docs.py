"""Guard against documentation rot in *project* Markdown only.

An ignored .venv or node_modules directory may contain arbitrary third-party
README files and broken relative links; those are not our documentation.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)#]+?)(#[^)]*)?\)")
EXTERNAL = ("http://", "https://", "mailto:")


def _project_markdown_files():
    """Prefer tracked Markdown, with a safe fallback for source archives."""
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "--cached", "--", "*.md"],
            check=True, capture_output=True, text=True,
        )
        tracked = [
            ROOT / name for name in result.stdout.splitlines()
            if name.endswith(".md")
        ]
        if tracked:
            return tracked
    except (OSError, subprocess.CalledProcessError):
        pass
    # Without .git (e.g. a packaged source distribution), restrict the search
    # to the documented, first-party locations instead of recursively crawling
    # vendored dependencies / ignored directories.
    return list(ROOT.glob("*.md")) + list((ROOT / "docs").glob("*.md"))


def _broken_links(md_files):
    broken = []
    for md in md_files:
        text = md.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            target = match.group(1).strip()
            if not target or target.startswith(EXTERNAL) or target.startswith("/"):
                continue
            if not (md.parent / target).exists():
                broken.append(f"{md.relative_to(ROOT)} -> {target}")
    return broken


def test_relative_markdown_links_resolve():
    broken = _broken_links(_project_markdown_files())
    assert not broken, "broken relative links: " + "; ".join(broken)


def test_ignored_venv_markdown_not_crawled(tmp_path, monkeypatch):
    monkeypatch.setattr("test_docs.ROOT", tmp_path)
    (tmp_path / "README.md").write_text("[guide](docs/guide.md)\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("All good\n", encoding="utf-8")
    ignored = tmp_path / ".venv" / "lib"
    ignored.mkdir(parents=True)
    (ignored / "README.md").write_text("[broken](missing.md)\n", encoding="utf-8")
    assert _broken_links(_project_markdown_files()) == []
