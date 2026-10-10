"""Guards for the vendored Pixel Agents renderer (pixel-client → web/pixel).

The renderer is third-party MIT code with CC0 sprites (see NOTICE.md). These
tests fail if the build output goes missing, if a CDN/telemetry reference
sneaks into the bundle, or if the route stops being auth-guarded.
"""

from pathlib import Path

from conftest import TOKEN, http

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "pixel"
SRC = ROOT / "pixel-client"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_source_and_license_present():
    assert (SRC / "package.json").is_file()
    assert (SRC / "src" / "hermesBridge.ts").is_file()
    license_text = (SRC / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text


def test_built_bundle_present():
    assert (DIST / "index.html").is_file(), "run `npm run build` in pixel-client"
    js = list((DIST / "assets").glob("index-*.js"))
    assert js, "built JS bundle missing"


def test_no_sourcemaps_shipped():
    assert not list(DIST.rglob("*.map")), "source maps must not be published"


def test_no_cdn_or_telemetry_in_bundle():
    blob = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in DIST.rglob("*.js"))
    for bad in ("cdnjs", "unpkg", "jsdelivr", "google-analytics", "googletagmanager", "sentry-cdn"):
        assert bad not in blob, f"unexpected external reference: {bad}"


def test_sprite_assets_present():
    for i in range(6):
        f = DIST / "assets" / "characters" / f"char_{i}.png"
        assert f.is_file() and f.read_bytes()[:8] == PNG_MAGIC


def test_attribution_in_notice():
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8")
    assert "pixel-agents-hq/pixel-agents" in notice
    assert "Epsilondelta-ai/pixel-agents-web" in notice
    assert "jik-a-4.itch.io" in notice


def test_pixel_route_requires_auth(server):
    assert http(server, "/pixel/index.html")[0] == 401
    status, headers, body = http(server, "/pixel/index.html", token=TOKEN)
    assert status == 200
    assert "text/html" in headers["Content-Type"]
    assert "/pixel/assets/" in body


def test_pixel_bundle_requires_auth(server):
    import re
    paths = re.findall(r'src="([^"]+\.js)"', http(server, "/pixel/index.html", token=TOKEN)[2])
    assert paths, "no bundle script referenced"
    assert http(server, paths[0])[0] == 401
