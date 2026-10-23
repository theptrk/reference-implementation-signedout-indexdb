import json
import time
from unittest.mock import Mock
from unittest.mock import patch
from urllib.parse import parse_qs
from urllib.parse import urlparse

import pytest
from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials

from . import google
from .models import GoogleCalendarConnection

pytestmark = pytest.mark.django_db


@pytest.fixture
def connected_client(client, user, settings):
    client.force_login(user)
    settings.GOOGLE_CLIENT_ID = "test-client"
    settings.GOOGLE_CLIENT_SECRET = "test-secret"
    settings.GOOGLE_TOKEN_ENCRYPTION_KEY = Fernet.generate_key().decode()
    return client


def test_integration_requires_login(client):
    assert client.get("/integrations/").status_code == 302


def test_connect_uses_separate_calendar_consent_and_pkce(connected_client):
    assert connected_client.get("/integrations/google/connect/").status_code == 405
    response = connected_client.post("/integrations/google/connect/")
    query = parse_qs(urlparse(response.url).query)
    assert query["scope"] == [google.SCOPE]
    assert query["access_type"] == ["offline"]
    assert query["code_challenge_method"] == ["S256"]
    assert connected_client.session["calendar_oauth"]["verifier"]


def test_callback_rejects_wrong_state_and_replay(connected_client):
    connected_client.post("/integrations/google/connect/")
    with patch.object(google, "flow") as flow:
        connected_client.get("/integrations/google/callback/?state=wrong&code=fake")
        assert not flow.called
    assert "calendar_oauth" not in connected_client.session
    assert not GoogleCalendarConnection.objects.exists()


def test_callback_stores_encrypted_credentials(connected_client, user, settings):
    connected_client.post("/integrations/google/connect/")
    state = connected_client.session["calendar_oauth"]["state"]
    credentials = Credentials(
        token="access-token",
        refresh_token="refresh-token",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="test-client",
        client_secret="test-secret",
        scopes=[google.SCOPE],
    )
    with patch.object(google, "flow", return_value=Mock(credentials=credentials)):
        response = connected_client.get(
            "/integrations/google/callback/", {"state": state, "code": "code"}
        )
    assert response.status_code == 302
    saved = GoogleCalendarConnection.objects.get(user=user).encrypted_credentials
    assert "refresh-token" not in saved
    decoded = json.loads(
        Fernet(settings.GOOGLE_TOKEN_ENCRYPTION_KEY.encode()).decrypt(saved.encode())
    )
    assert decoded["refresh_token"] == "refresh-token"
    assert "client_secret" not in decoded


def test_callback_rejects_expired_or_denied_consent(connected_client):
    connected_client.post("/integrations/google/connect/")
    session = connected_client.session
    pending = session["calendar_oauth"]
    pending["created"] = time.time() - 700
    session["calendar_oauth"] = pending
    session.save()
    with patch.object(google, "flow") as flow:
        connected_client.get(
            "/integrations/google/callback/",
            {"state": pending["state"], "code": "code"},
        )
        assert not flow.called
    connected_client.post("/integrations/google/connect/")
    state = connected_client.session["calendar_oauth"]["state"]
    connected_client.get(
        "/integrations/google/callback/", {"state": state, "error": "access_denied"}
    )
    assert not GoogleCalendarConnection.objects.exists()


def test_events_and_disconnect_are_owner_scoped(connected_client, user):
    connection = GoogleCalendarConnection.objects.create(
        user=user, encrypted_credentials="encrypted"
    )
    with patch.object(
        google,
        "upcoming",
        return_value=[
            {"summary": "<script>unsafe</script>", "start": {"date": "2026-10-24"}}
        ],
    ):
        response = connected_client.get("/integrations/")
        assert response.status_code == 200
        assert b"&lt;script&gt;" in response.content
    assert connected_client.get("/integrations/google/disconnect/").status_code == 405
    assert connected_client.post("/integrations/google/disconnect/").status_code == 302
    assert not GoogleCalendarConnection.objects.filter(pk=connection.pk).exists()
