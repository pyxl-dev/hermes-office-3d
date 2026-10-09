import os

from hermes_office.config import load_env_file


def _clear(*keys):
    for k in keys:
        os.environ.pop(k, None)


def test_missing_file_is_a_noop(tmp_path):
    assert load_env_file(str(tmp_path / "nope.env")) == 0


def test_parses_pairs_comments_and_quotes(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "# a comment\n"
        "\n"
        "HERMES_X_ONE=plain\n"
        "export HERMES_X_TWO='quoted value'\n"
        "HERMES_X_THREE=\"double\"\n"
        "not a valid line\n"
        "9BAD=ignored\n"
    )
    _clear("HERMES_X_ONE", "HERMES_X_TWO", "HERMES_X_THREE", "9BAD")
    loaded = load_env_file(str(env))
    assert loaded == 3
    assert os.environ["HERMES_X_ONE"] == "plain"
    assert os.environ["HERMES_X_TWO"] == "quoted value"
    assert os.environ["HERMES_X_THREE"] == "double"
    assert "9BAD" not in os.environ
    _clear("HERMES_X_ONE", "HERMES_X_TWO", "HERMES_X_THREE")


def test_real_env_wins_over_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("HERMES_X_WINFROMFILE=file\n")
    os.environ["HERMES_X_WINFROMFILE"] = "shell"
    try:
        load_env_file(str(env))
        assert os.environ["HERMES_X_WINFROMFILE"] == "shell"
    finally:
        _clear("HERMES_X_WINFROMFILE")
