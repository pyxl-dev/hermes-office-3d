"""Guards for the Pixel Agents-style POC assets.

These files are bundled third-party art (Pixel Agents / MetroCity, see NOTICE.md).
If someone strips the attribution or the assets go missing, CI should say so.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIXEL = ROOT / "web" / "pixel"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_pixel_poc_files_exist():
    assert (PIXEL / "index.html").is_file()
    assert (PIXEL / "pixel.js").is_file()
    assert (PIXEL / "assets" / "walls.png").is_file()


def test_character_sheets_are_png():
    for i in range(6):
        f = PIXEL / "assets" / "characters" / f"char_{i}.png"
        assert f.is_file(), f"missing {f}"
        assert f.read_bytes()[:8] == PNG_MAGIC, f"{f} is not a PNG"


def test_attribution_present():
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    assert "pixel-agents-hq/pixel-agents" in notice
    assert "jik-a-4.itch.io/metrocity" in notice
    assert "CC0" in notice


def test_frontend_uses_friendly_labels_only():
    js = (PIXEL / "pixel.js").read_text(encoding="utf-8")
    # labels are "Session N" / "Subagent N" — never raw ids or hashes
    assert "Session " in js and "Subagent " in js
