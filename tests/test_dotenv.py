import os

from hermes_office.config import load_env_file


def test_missing_file_is_a_noop(tmp_path):
    assert load_env_file(str(tmp_path / "missing.env")) == 0


def test_parses_supported_pairs_comments_and_quotes(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "HERMES_OFFICE_PORT=8765  # local listener\n"
        "export HERMES_API_BASE='http://127.0.0.1:8642' # gateway\n"
        'HERMES_OFFICE_TOKEN="safe-token"  # browser login\n'
        "HERMES_OFFICE_MAX_ACTORS=30\n"
        "HERMES_UNSUPPORTED_KEY=ignored\n"
        "not a valid line\n"
        "9BAD=ignored\n",
        encoding="utf-8",
    )
    keys = (
        "HERMES_OFFICE_PORT", "HERMES_API_BASE",
        "HERMES_OFFICE_TOKEN", "HERMES_OFFICE_MAX_ACTORS",
        "HERMES_UNSUPPORTED_KEY",
    )
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    assert load_env_file(str(env)) == 4
    assert os.environ["HERMES_OFFICE_PORT"] == "8765"
    assert os.environ["HERMES_API_BASE"] == "http://127.0.0.1:8642"
    assert os.environ["HERMES_OFFICE_TOKEN"] == "safe-token"
    assert os.environ["HERMES_OFFICE_MAX_ACTORS"] == "30"
    assert "HERMES_UNSUPPORTED_KEY" not in os.environ


def test_unknown_process_wide_keys_are_not_exported(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "HTTP_PROXY=http://untrusted.invalid:8888\n"
        "HTTPS_PROXY=http://untrusted.invalid:8888\n"
        "PYTHONPATH=/untrusted/path\n"
        "HERMES_API_KEY=synthetic-not-a-real-key\n",
        encoding="utf-8",
    )
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "PYTHONPATH", "HERMES_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert load_env_file(str(env)) == 1
    assert os.environ["HERMES_API_KEY"] == "synthetic-not-a-real-key"
    assert "HTTP_PROXY" not in os.environ
    assert "HTTPS_PROXY" not in os.environ
    assert "PYTHONPATH" not in os.environ


def test_comments_do_not_mutate_unquoted_values(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "HERMES_OFFICE_TOKEN=mytoken # office login\n"
        "HERMES_API_BASE=http://localhost:8642/#fragment\n"
        "HERMES_OFFICE_PORT='8765'  # allowed trailing comment\n",
        encoding="utf-8",
    )
    for key in ("HERMES_OFFICE_TOKEN", "HERMES_API_BASE", "HERMES_OFFICE_PORT"):
        monkeypatch.delenv(key, raising=False)
    assert load_env_file(str(env)) == 3
    assert os.environ["HERMES_OFFICE_TOKEN"] == "mytoken"
    assert os.environ["HERMES_API_BASE"] == "http://localhost:8642/#fragment"
    assert os.environ["HERMES_OFFICE_PORT"] == "8765"


def test_malformed_quote_ignored(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        'HERMES_OFFICE_TOKEN="unterminated\n'
        "HERMES_OFFICE_PORT='8765' extra\n"
        "HERMES_OFFICE_MAX_ACTORS=5\n",
        encoding="utf-8",
    )
    for key in ("HERMES_OFFICE_TOKEN", "HERMES_OFFICE_PORT", "HERMES_OFFICE_MAX_ACTORS"):
        monkeypatch.delenv(key, raising=False)
    assert load_env_file(str(env)) == 1
    assert "HERMES_OFFICE_TOKEN" not in os.environ
    assert "HERMES_OFFICE_PORT" not in os.environ
    assert os.environ["HERMES_OFFICE_MAX_ACTORS"] == "5"


def test_real_env_wins_over_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("HERMES_OFFICE_PORT=9000\n")
    monkeypatch.setenv("HERMES_OFFICE_PORT", "8765")
    assert load_env_file(str(env)) == 0
    assert os.environ["HERMES_OFFICE_PORT"] == "8765"
