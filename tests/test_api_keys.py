"""API keys — the model and service layer behind ADR 0006.

Endpoint-level behaviour (auth, scopes, throttling) lives in tests/api/test_api_keys.py;
this file is the credential itself: issuing, resolving, revoking, expiring.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import ApiKeyScope
from apps.accounts.services import (
    RegistrationError,
    authenticate_api_key,
    issue_api_key,
    revoke_api_key,
)


def test_issuing_a_key_returns_the_secret_exactly_once(user):
    key, secret = issue_api_key(owner=user, label="laptop")

    assert secret.startswith("cern_live_")
    assert key.prefix == secret[:14]
    assert key.key_hash != secret
    # The secret itself is nowhere on the stored row.
    assert secret not in vars(key).values()


def test_a_freshly_issued_key_authenticates(user):
    _key, secret = issue_api_key(owner=user, label="laptop")

    resolved = authenticate_api_key(secret)

    assert resolved is not None
    assert resolved.owner == user


@pytest.mark.parametrize(
    "bad",
    ["", "not-a-key-at-all", "cern_live_wrongsecretwrongsecret", "cern_test_wrongprefix12345678"],
)
def test_a_bad_secret_does_not_authenticate(user, bad):
    issue_api_key(owner=user, label="laptop")
    assert authenticate_api_key(bad) is None


def test_a_revoked_key_stops_authenticating(user):
    key, secret = issue_api_key(owner=user, label="laptop")
    assert authenticate_api_key(secret) is not None

    revoke_api_key(key)

    assert authenticate_api_key(secret) is None


def test_revoking_twice_is_idempotent(user):
    key, _secret = issue_api_key(owner=user, label="laptop")

    assert revoke_api_key(key) is True
    assert revoke_api_key(key) is False


def test_an_expired_key_does_not_authenticate(user):
    key, secret = issue_api_key(owner=user, label="laptop", expires_in_days=1)
    key.expires_at = timezone.now() - timedelta(days=1)
    key.save(update_fields=["expires_at"])

    assert authenticate_api_key(secret) is None


def test_a_key_for_an_inactive_user_does_not_authenticate(user):
    _key, secret = issue_api_key(owner=user, label="laptop")
    user.is_active = False
    user.save(update_fields=["is_active"])

    assert authenticate_api_key(secret) is None


def test_unknown_scope_is_rejected(user):
    with pytest.raises(RegistrationError, match="scope"):
        issue_api_key(owner=user, label="laptop", scopes=("delete",))


def test_design_scope_implies_read(user):
    key, _secret = issue_api_key(owner=user, label="laptop", scopes=(ApiKeyScope.DESIGN,))

    assert key.has_scope(ApiKeyScope.READ)
    assert key.has_scope(ApiKeyScope.DESIGN)


def test_read_scope_does_not_imply_design(user):
    key, _secret = issue_api_key(owner=user, label="laptop", scopes=(ApiKeyScope.READ,))

    assert key.has_scope(ApiKeyScope.READ)
    assert not key.has_scope(ApiKeyScope.DESIGN)
