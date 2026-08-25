"""Shared pytest fixtures."""

import pytest


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        username="researcher",
        email="researcher@example.org",
        password="test-password-123",
    )
