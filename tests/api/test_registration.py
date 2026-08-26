"""Registration and admin approval.

Accounts are created inactive and a staff member activates them. No email anywhere.
"""

import json
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.accounts.services import RegistrationError, approve_user, register_user

GOOD = {
    "username": "rosalind",
    "email": "Rosalind@Example.org",
    "password": "helix-photo-51",
    "full_name": "Rosalind Franklin",
}


def _register(client, **overrides):
    return client.post(
        "/api/auth/register",
        data=json.dumps({**GOOD, **overrides}),
        content_type="application/json",
    )


def _login(client, username="rosalind", password="helix-photo-51"):
    return client.post(
        "/api/auth/login",
        data=json.dumps({"username": username, "password": password}),
        content_type="application/json",
    )


# --- Registering ------------------------------------------------------------------


def test_registering_creates_a_pending_account(client, db):
    response = _register(client)
    body = response.json()

    assert response.status_code == 201
    assert body["pending_approval"] is True
    assert "approve" in body["message"]

    user = get_user_model().objects.get(username="rosalind")
    assert not user.is_active, "a new account must not be usable until approved"
    assert user.get_full_name() == "Rosalind Franklin"


def test_registering_does_not_sign_you_in(client, db):
    """The account is not usable yet, so establishing a session would be a lie."""
    _register(client)
    assert client.get("/api/auth/me").status_code == 401


def test_email_is_stored_lowercase(client, db):
    _register(client)
    assert get_user_model().objects.get(username="rosalind").email == "rosalind@example.org"


def test_registering_needs_no_authentication(client, db):
    assert _register(client).status_code == 201


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("username", "ab", "at least 3"),
        ("email", "", "email address is required"),
        ("password", "abcdefgh", "too common"),
        ("password", "12345678", "entirely numeric"),
    ],
)
def test_bad_registrations_are_refused_with_a_reason(client, db, field, value, expected):
    response = _register(client, **{field: value})

    assert response.status_code == 422
    assert expected in response.json()["error"]["message"].lower()


def test_a_taken_username_is_refused(client, db, user):
    response = _register(client, username="researcher")

    assert response.status_code == 422
    assert "already taken" in response.json()["error"]["message"]


def test_username_uniqueness_ignores_case(client, db):
    _register(client)
    response = _register(client, username="ROSALIND", email="other@example.org")

    assert response.status_code == 422
    assert "already taken" in response.json()["error"]["message"]


def test_a_taken_email_is_refused(client, db):
    _register(client)
    response = _register(client, username="somebody-else", email="rosalind@example.org")

    assert response.status_code == 422
    assert "email address already exists" in response.json()["error"]["message"]


# --- Signing in before approval ---------------------------------------------------


def test_a_pending_account_cannot_sign_in(client, db):
    _register(client)
    response = _login(client)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "pending_approval"
    assert "approve" in response.json()["error"]["message"]


def test_a_wrong_password_on_a_pending_account_is_just_wrong(client, db):
    """Knowing an account is pending requires knowing its password, so this is not a
    way to discover which accounts exist."""
    _register(client)
    response = _login(client, password="not-the-password")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_an_unknown_user_and_a_wrong_password_are_indistinguishable(client, db, user):
    unknown = _login(client, username="nobody", password="whatever").json()
    wrong = _login(client, username="researcher", password="whatever").json()

    assert unknown == wrong


# --- Approval ---------------------------------------------------------------------


def test_an_approved_account_can_sign_in(client, db):
    _register(client)
    approve_user(get_user_model().objects.get(username="rosalind"))

    response = _login(client)

    assert response.status_code == 200
    assert response.json()["username"] == "rosalind"
    assert client.get("/api/auth/me").status_code == 200


def test_approving_twice_is_harmless(db):
    user = register_user(username="alice", email="a@example.org", password="helix-photo-51")

    assert approve_user(user) is True
    assert approve_user(user) is False


def test_registration_service_rejects_a_blank_username(db):
    with pytest.raises(RegistrationError, match="Choose a username"):
        register_user(username="   ", email="a@example.org", password="helix-photo-51")


# --- Admin ------------------------------------------------------------------------


def test_admin_lists_and_approves_pending_accounts(client, db, staff_user):
    _register(client)
    client.force_login(staff_user)

    listing = client.get("/admin/accounts/user/?approval=pending")
    assert listing.status_code == 200
    assert "rosalind" in listing.content.decode()

    pending = get_user_model().objects.get(username="rosalind")
    response = client.post(
        "/admin/accounts/user/",
        {"action": "approve_selected", "_selected_action": [str(pending.pk)]},
        follow=True,
    )

    assert response.status_code == 200
    pending.refresh_from_db()
    assert pending.is_active


def test_admin_warns_when_accounts_are_waiting(client, db, staff_user):
    _register(client)
    client.force_login(staff_user)

    body = client.get("/admin/accounts/user/").content.decode()
    assert "waiting for approval" in body


# --- CLI --------------------------------------------------------------------------


def test_the_cli_lists_pending_accounts(client, db):
    _register(client)
    out = StringIO()
    call_command("pending_accounts", stdout=out)

    text = out.getvalue()
    assert "rosalind" in text
    assert "rosalind@example.org" in text


def test_the_cli_approves_by_username(client, db):
    _register(client)
    call_command("pending_accounts", approve=["rosalind"], stdout=StringIO())

    assert get_user_model().objects.get(username="rosalind").is_active


def test_the_cli_reports_an_unknown_username(db):
    err = StringIO()
    call_command("pending_accounts", approve=["ghost"], stderr=err)
    assert "no such account" in err.getvalue()


def test_the_cli_says_so_when_nothing_is_waiting(db):
    out = StringIO()
    call_command("pending_accounts", stdout=out)
    assert "No accounts are waiting" in out.getvalue()
