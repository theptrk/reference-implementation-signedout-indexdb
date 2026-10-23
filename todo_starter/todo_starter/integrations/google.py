import json

from cryptography.fernet import Fernet
from django.conf import settings
from django.utils import timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from requests import Session

SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"


def configured():
    return bool(
        settings.GOOGLE_CLIENT_ID
        and settings.GOOGLE_CLIENT_SECRET
        and settings.GOOGLE_TOKEN_ENCRYPTION_KEY
    )


def cipher():
    return Fernet(settings.GOOGLE_TOKEN_ENCRYPTION_KEY.encode())


def flow(**kwargs):
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=[SCOPE],
        redirect_uri=settings.GOOGLE_CALENDAR_REDIRECT_URI,
        **kwargs,
    )


def save_credentials(connection, credentials):
    # Client secret comes from settings; do not duplicate it in the database.
    data = json.loads(credentials.to_json())
    data.pop("client_secret", None)
    connection.encrypted_credentials = (
        cipher().encrypt(json.dumps(data).encode()).decode()
    )
    connection.save()


def upcoming(connection):
    data = json.loads(cipher().decrypt(connection.encrypted_credentials.encode()))
    data["client_secret"] = settings.GOOGLE_CLIENT_SECRET
    credentials = Credentials.from_authorized_user_info(data)
    if not credentials.valid:
        with Session() as session:
            credentials.refresh(Request(session=session))
        save_credentials(connection, credentials)
    with Session() as session:
        response = session.get(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={"Authorization": f"Bearer {credentials.token}"},
            params={
                "timeMin": timezone.now().isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": 10,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json().get("items", [])
