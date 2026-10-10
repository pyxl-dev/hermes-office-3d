"""Regression guard for the avatar-visibility fix in the vendored renderer.

Bug (PR #7): with the official layout, the sanitized API produced six agents but
ZERO characters rendered. Root cause: agents arriving after `layoutLoaded` were
added with the Matrix "materialise" spawn effect (`skipSpawnEffect` unset), which
left them stuck in the spawn state and effectively invisible (verified in-browser:
all six had `matrixEffect: "spawn"` with valid seats/positions).

Fix: add snapshot-derived agents with `skipSpawnEffect = true` (the upstream's own
restore semantics). These tests fail if that adaptation is reverted.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "pixel-client" / "src"
DIST = ROOT / "web" / "pixel"


def _hook_src() -> str:
    return (SRC / "hooks" / "useExtensionMessages.ts").read_text(encoding="utf-8")


def test_agents_added_without_spawn_effect():
    src = _hook_src()
    assert "os.addAgent(id, undefined, undefined, undefined, true, folderName)" in src, (
        "snapshot agents must skip the Matrix spawn effect or they render invisible"
    )
    # the interactive/spawned path must keep its effect (we only change restore)
    assert "os.addAgent(id, undefined, undefined, undefined, undefined, folderName)" not in src


def test_hermes_bridge_emits_agents_before_layout():
    src = (SRC / "hermesBridge.ts").read_text(encoding="utf-8")
    # Runtime order in the ready handler: poll (emits agents) before any layout load.
    ready = src.index("await handleReady()")
    poll_at = src.index("await poll()", ready)
    restore_at = src.index("restoreSavedLayout()", poll_at)
    assert poll_at < restore_at, "agents must be emitted before a layout is loaded"


def test_bridge_only_animates_verified_tool_activity():
    """The bridge may now emit tool events, but only from server-verified state.

    It must never invent activity: tool events are gated on the sanitized
    run_activity.tool_active flag, and every other path stays idle.
    """
    src = (SRC / "hermesBridge.ts").read_text(encoding="utf-8")
    assert "run_activity" in src and "tool_active" in src
    # the start path is reachable only behind the verified flag
    start = src.index("agentToolStart")
    guard = src.rindex("activity?.tool_active", 0, start)
    assert guard != -1, "agentToolStart must sit behind the verified activity flag"
    # neutral fallback for anything unverified
    assert "status: 'idle'" in src
    # no raw tool name or preview may be forwarded
    for forbidden in ("msg.preview", "preview:", "toolName:", "arguments"):
        assert forbidden not in src, f"{forbidden} must not be sent to the renderer"


def test_built_bundle_has_no_sourcemaps_or_debug_hook():
    assert not list(DIST.rglob("*.map"))
    blob = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in DIST.rglob("*.js"))
    assert "__osInfo" not in blob, "temporary debug hook must not ship"
