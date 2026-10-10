"""Regression guards for the five P2 review findings on the pixel-art client."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = (ROOT / "hermes_office" / "server.py").read_text(encoding="utf-8")
MAIN = (ROOT / "pixel-client" / "src" / "main.tsx").read_text(encoding="utf-8")
BRIDGE = (ROOT / "pixel-client" / "src" / "hermesBridge.ts").read_text(encoding="utf-8")


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
