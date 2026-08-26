"""Account registration and approval.

New accounts are created **inactive** and stay that way until a staff member approves
them in Django admin. No email is involved anywhere: at a few dozen users, a person on
the team is always reachable, and SMTP credentials would be one more thing to hold
correctly on the VPS (docs/software-design.md §2, rule 10).
"""

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)


class RegistrationError(Exception):
    """The account could not be created. The message is safe to show the applicant."""


@transaction.atomic
def register_user(*, username: str, email: str, password: str, full_name: str = ""):
    """Create a pending account.

    Returns the user with ``is_active=False``. They cannot sign in until a staff member
    approves them.
    """
    model = get_user_model()

    username = username.strip()
    email = email.strip().lower()

    if not username:
        raise RegistrationError("Choose a username.")
    if len(username) < 3:
        raise RegistrationError("Usernames must be at least 3 characters.")
    if len(password) < 8:
        raise RegistrationError("Passwords must be at least 8 characters.")
    if not email:
        raise RegistrationError("An email address is required, so we know who you are.")

    # Usernames are unique and the applicant has to be told, so this necessarily
    # reveals that one is taken. Email is checked case-insensitively for the same reason.
    if model.objects.filter(username__iexact=username).exists():
        raise RegistrationError("That username is already taken.")
    if model.objects.filter(email__iexact=email).exists():
        raise RegistrationError("An account with that email address already exists.")

    first_name, _, last_name = full_name.strip().partition(" ")

    user = model(
        username=username,
        email=email,
        first_name=first_name[:150],
        last_name=last_name[:150],
        # The whole point: approval is a deliberate human act.
        is_active=False,
    )

    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise RegistrationError(" ".join(exc.messages)) from None

    user.set_password(password)

    try:
        user.save()
    except IntegrityError:
        raise RegistrationError("That username is already taken.") from None

    logger.info("Registration request from %s (%s) awaiting approval", username, email)
    return user


def approve_user(user) -> bool:
    """Activate a pending account. Returns False if it was already active."""
    if user.is_active:
        return False

    user.is_active = True
    user.save(update_fields=["is_active"])
    logger.info("Account %s approved", user.username)
    return True


def pending_users():
    """Everyone waiting for approval, oldest request first."""
    return get_user_model().objects.filter(is_active=False).order_by("date_joined")
