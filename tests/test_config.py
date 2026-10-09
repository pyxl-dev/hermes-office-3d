import pytest

from hermes_office.config import Settings


def test_token_may_be_generated():
    s = Settings(office_token="")
    token = s.ensure_token()
    assert token and len(token) >= 20


def test_token_with_illegal_chars_is_rejected():
    with pytest.raises(ValueError):
        Settings(office_token="bad token with spaces").ensure_token()
    with pytest.raises(ValueError):
        Settings(office_token="semi;colon").ensure_token()


def test_safe_token_accepted():
    assert Settings(office_token="aZ09-_.X").ensure_token() == "aZ09-_.X"


def test_demo_mode_flag():
    assert Settings(hermes_api_key="").demo_mode is True
    assert Settings(hermes_api_key="x").demo_mode is False
