from django.test import RequestFactory

from api.security import _auth_client_address


def test_untrusted_peer_cannot_spoof_auth_identity(settings):
    settings.AUTH_TRUSTED_PROXY_ADDRESSES = ["127.0.0.1"]
    request = RequestFactory().get(
        "/", REMOTE_ADDR="192.0.2.10", HTTP_X_CERNAL_CLIENT_IP="198.51.100.1"
    )
    assert _auth_client_address(request) == "192.0.2.10"


def test_trusted_proxy_keeps_distinct_clients_separate(settings):
    settings.AUTH_TRUSTED_PROXY_ADDRESSES = ["127.0.0.1"]
    factory = RequestFactory()
    assert [
        _auth_client_address(
            factory.get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_CERNAL_CLIENT_IP=address)
        )
        for address in ("198.51.100.1", "198.51.100.2")
    ] == ["198.51.100.1", "198.51.100.2"]


def test_invalid_or_missing_proxy_address_uses_peer(settings):
    settings.AUTH_TRUSTED_PROXY_ADDRESSES = ["127.0.0.1"]
    factory = RequestFactory()
    for supplied in ("", "198.51.100.1, 198.51.100.2", "not-an-ip"):
        request = factory.get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_CERNAL_CLIENT_IP=supplied)
        assert _auth_client_address(request) == "127.0.0.1"
