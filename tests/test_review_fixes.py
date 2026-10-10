"""Regression guards for the five P2 review findings on the pixel-art client."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = (ROOT / "hermes_office" / "server.py").read_text(encoding="utf-8")
MAIN = (ROOT / "pixel-client" / "src" / "main.tsx").read_text(encoding="utf-8")
BRIDGE = (ROOT / "pixel-client" / "src" / "hermesBridge.ts").read_text(encoding="utf-8")


def _fn(src: str, signature: str) -> str:
    """Extract a top-level function body by brace matching from its signature."""
    start = src.index(signature)
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start : i + 1]
    raise AssertionError("unbalanced braces")


def test_pixel_directory_serves_index_html():
    """1) /pixel/ returned 404 because only the explicit filename was served."""
    assert 'rel = "pixel/index.html"' in SERVER
    assert 'rel += "index.html"' in SERVER


def test_bridge_loads_the_saved_layout():
    """2) the layout saved to localStorage was never read back."""
    assert "restoreSavedLayout" in BRIDGE
    assert "localStorage.getItem('hermes-office-layout')" in BRIDGE
    assert "Array.isArray(layout?.furniture)" in BRIDGE


def test_inert_settings_controls_are_hidden():
    """3) Settings import/export had no handler in Hermes mode."""
    assert "hideInertSettings" in BRIDGE
    assert "aria-hidden" in BRIDGE


def test_degraded_api_is_not_reported_as_healthy():
    """4) degraded=true still showed a green LIVE badge."""
    assert "DISCONNECTED" in BRIDGE
    assert "setDegraded" in BRIDGE
    assert "probe?.degraded === true" in BRIDGE


def test_bridge_selected_by_build_mode_not_url():
    """5) /pixel/ in Vite dev selected the Hermes bridge by accident."""
    assert "!import.meta.env.DEV" in MAIN
    assert "window.location.pathname.startsWith('/pixel')" not in MAIN


def test_poll_updates_degraded_on_every_tick():
    """P2: degraded was only evaluated at startup, so a later outage showed green."""
    poll = _fn(BRIDGE, "async function poll()")
    assert "setDegraded(data?.degraded === true)" in poll
    assert "setDegraded(true)" in poll  # !res.ok and network failure


def test_network_failure_marks_degraded():
    poll = _fn(BRIDGE, "async function poll()")
    assert "catch {" in poll and "setDegraded(true)" in poll


def test_only_import_export_are_hidden_not_settings_or_save():
    """P2: the periodic hider matched 'settings'/'save' and broke the layout editor."""
    fn = _fn(BRIDGE, "function hideInertSettings")
    assert "/^(import|export)(\\s|$)/i" in fn
    for word in ("settings", "save", "load"):
        assert word not in fn.split("test(")[1].split(")")[0].lower(), f"{word} must not be hidden"
