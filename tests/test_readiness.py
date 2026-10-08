from unittest.mock import patch

import pytest
from django.db import OperationalError


@pytest.mark.django_db
def test_readiness_requires_worker(client):
    with patch("api.routers.meta.worker_available", return_value=False):
        response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    with patch("api.routers.meta.worker_available", return_value=True):
        assert client.get("/api/ready").status_code == 200


@pytest.mark.django_db
def test_readiness_hides_database_exception(client):
    with patch("api.routers.meta.connection.cursor", side_effect=OperationalError("secret")):
        response = client.get("/api/ready")
    assert response.status_code == 503
    assert b"secret" not in response.content


def test_liveness_does_not_require_database_or_worker(client):
    with patch("api.routers.meta.worker_available", side_effect=AssertionError("called")):
        assert client.get("/api/health").json() == {"status": "ok"}
