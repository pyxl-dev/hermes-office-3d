import pytest

from hermes_office.config import Settings
from hermes_office.server import build_server


def test_bind_refuses_non_loopback_by_default():
    with pytest.raises(ValueError):
        build_server(Settings(host="0.0.0.0", port=0, office_token="t", hermes_api_key=""))
    with pytest.raises(ValueError):
        build_server(Settings(host="192.168.1.10", port=0, office_token="t", hermes_api_key=""))


def test_bind_allows_loopback_hosts():
    for host in ("127.0.0.1", "localhost"):
        httpd = build_server(Settings(host=host, port=0, office_token="t", hermes_api_key=""))
        httpd.server_close()


def test_bind_allows_non_loopback_only_when_explicit():
    httpd = build_server(
        Settings(host="0.0.0.0", port=0, office_token="t", hermes_api_key="", allow_remote=True)
    )
    httpd.server_close()


def test_slow_sse_client_is_dropped_not_starved():
    from hermes_office.server import Store

    store = Store(Settings(host="127.0.0.1", port=0, office_token="t", hermes_api_key=""))
    q = store.subscribe()
    assert store.is_subscribed(q)
    for _ in range(20):  # never drained -> queue fills
        store.refresh()
    assert not store.is_subscribed(q)


def test_pseudonyms_stay_stable_across_background_refreshes():
    from hermes_office.server import Store

    store = Store(Settings(host="127.0.0.1", port=0, office_token="test", hermes_api_key=""))
    first = [a["id"] for a in store.payload()["actors"]]
    assert first
    for _ in range(3):
        second = [a["id"] for a in store.refresh()["actors"]]
        assert second == first
