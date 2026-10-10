"""Regression guards for the workstation-first seat ordering (Hermes adaptation).

The official layout has 12 seats: workstation chairs (adjacent to a desk) plus
lounge seating. Agents must take the workstation chairs first, and the ordering
must be deterministic so the same N agents always land on the same seats.

These tests check the DATA (layout + catalog) and the SOURCE adaptation; the
rendered result is verified by the DEMO screenshots in docs/screenshots/.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "web" / "pixel" / "assets"
SRC = ROOT / "pixel-client" / "src"


def _catalog():
    return json.loads((ASSETS / "furniture" / "furniture-catalog.json").read_text())


def _layout():
    return json.loads((ASSETS / "default-layout.json").read_text())


def _workstation_seats():
    cat = {a["id"]: a for a in _catalog()["assets"]}
    layout = _layout()
    desk_tiles = set()
    for item in layout["furniture"]:
        e = cat.get(item["type"])
        if not e or not e.get("isDesk"):
            continue
        for dr in range(e.get("footprintH", 1)):
            for dc in range(e.get("footprintW", 1)):
                desk_tiles.add((item["col"] + dc, item["row"] + dr))
    seats = []
    for item in layout["furniture"]:
        e = cat.get(item["type"])
        if not e or e.get("category") != "chairs":
            continue
        for dr in range(e.get("footprintH", 1)):
            for dc in range(e.get("footprintW", 1)):
                col, row = item["col"] + dc, item["row"] + dr
                if any((col + dc2, row + dr2) in desk_tiles
                       for dc2, dr2 in ((0, -1), (0, 1), (-1, 0), (1, 0))):
                    seats.append((col, row))
    return seats


def test_enough_workstation_seats_for_the_agent_cap():
    seats = _workstation_seats()
    assert len(seats) >= 8, f"need >=8 workstation seats for the 8-agent cap, got {len(seats)}"


def test_workstation_seats_are_unique():
    seats = _workstation_seats()
    assert len(seats) == len(set(seats)), "duplicate workstation seats would overlap avatars"


def test_source_orders_workstation_seats_first():
    src = (SRC / "office" / "layout" / "layoutSerializer.ts").read_text(encoding="utf-8")
    assert "workstationUids" in src
    assert "Rebuild in workstation-first order" in src


def test_camera_fits_the_layout_to_the_viewport():
    src = (SRC / "office" / "components" / "OfficeCanvas.tsx").read_text(encoding="utf-8")
    # fits the occupied bbox (ignoring void rows), in device pixels, retried until sized
    assert "fitToRoom" in src
    assert "canvas.width / bboxW" in src
    assert "const VOID = 255" in src
    assert "onZoomChange(z)" in src


def test_chair_seat_uses_the_bottom_tile_only():
    """A chair is ONE seat at its bottom tile.

    Upstream turned every footprint tile into a seat, so a 1x2 chair produced two
    seats and the agent was drawn on the chair's top tile while the sprite extended
    below - reading as an agent standing above an empty chair.
    """
    src = (SRC / "office" / "layout" / "layoutSerializer.ts").read_text(encoding="utf-8")
    assert "const seatRow = item.row + entry.footprintH - 1" in src
    # the seat loop iterates columns only, never rows
    assert "for (let dc = 0; dc < entry.footprintW; dc++) {" in src
    assert "const seatUid = seatCount === 0 ? item.uid" in src


def test_workstation_flag_uses_any_chair_tile():
    """Adjacency must consider the whole chair, since the seat sits on the bottom tile."""
    src = (SRC / "office" / "layout" / "layoutSerializer.ts").read_text(encoding="utf-8")
    assert "let isWorkstationChair = false" in src
    assert "if (isWorkstationChair) workstationUids.add(seatUid)" in src
