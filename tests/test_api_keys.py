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
    regenerate_api_key,
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


# --- Regeneration ("reset" in the web UI) -------------------------------------------


def test_regenerating_returns_a_new_secret(user):
    key, old_secret = issue_api_key(owner=user, label="laptop")

    _key, new_secret = regenerate_api_key(key)

    assert new_secret != old_secret
    assert new_secret.startswith("cern_live_")


def test_regenerating_invalidates_the_old_secret_immediately(user):
    key, old_secret = issue_api_key(owner=user, label="laptop")
    assert authenticate_api_key(old_secret) is not None

    regenerate_api_key(key)

    assert authenticate_api_key(old_secret) is None


def test_regenerating_makes_the_new_secret_work(user):
    key, _old_secret = issue_api_key(owner=user, label="laptop")

    _key, new_secret = regenerate_api_key(key)

    resolved = authenticate_api_key(new_secret)
    assert resolved is not None
    assert resolved.id == key.id


def test_regenerating_keeps_identity_label_and_scopes(user):
    key, _secret = issue_api_key(owner=user, label="laptop", scopes=(ApiKeyScope.READ,))
    original_id = key.id

    key, _new_secret = regenerate_api_key(key)

    assert key.id == original_id
    assert key.label == "laptop"
    assert key.scopes == [ApiKeyScope.READ]


def test_regenerating_a_revoked_key_reactivates_it(user):
    key, _secret = issue_api_key(owner=user, label="laptop")
    revoke_api_key(key)
    assert key.revoked_at is not None

    key, new_secret = regenerate_api_key(key)

    assert key.revoked_at is None
    assert authenticate_api_key(new_secret) is not None
