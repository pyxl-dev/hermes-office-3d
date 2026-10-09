from hermes_office.redact import Pseudonymiser, redact_text, scrub_actor


def test_pseudonym_is_stable_within_a_run():
    p = Pseudonymiser(salt=b"fixed-salt")
    assert p("session-1") == p("session-1")
    assert p("session-1") != p("session-2")
    assert p("session-1").startswith("s-")


def test_pseudonym_differs_across_salts():
    assert Pseudonymiser(salt=b"a")("x") != Pseudonymiser(salt=b"b")("x")


def test_pseudonym_never_contains_raw_value():
    raw = "20261009_abcdef_secret_session"
    out = Pseudonymiser()(raw)
    assert raw not in out
    assert out != raw


def test_pseudonym_empty_input():
    assert Pseudonymiser()(None) == ""
    assert Pseudonymiser()("") == ""


def test_scrub_actor_drops_forbidden_keys():
    actor = {
        "id": "s-abc",
        "state": "active",
        "title": "my private session",
        "preview": "leak",
        "system_prompt": "leak",
        "path": "/Users/someone/secret",
    }
    clean = scrub_actor(actor)
    for forbidden in ("title", "preview", "system_prompt", "path"):
        assert forbidden not in clean
    assert clean["id"] == "s-abc"


def test_redact_text_removes_paths_and_tokens():
    out = redact_text("error in /Users/example/Projects/secret at token abcdefghijklmnopqrstuvwxyz012345")
    assert "/Users/example" not in out
    assert "[path]" in out
    assert "[token]" in out
