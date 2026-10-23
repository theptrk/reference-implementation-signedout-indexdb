import secrets
import time

from cryptography.fernet import InvalidToken
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_variables
from django.views.decorators.http import require_POST
from google.auth.exceptions import GoogleAuthError
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException

from . import google
from .models import GoogleCalendarConnection

OAUTH_MAX_AGE = 600


@login_required
@never_cache
def index(request):
    connection = GoogleCalendarConnection.objects.filter(user=request.user).first()
    events = []
    if connection:
        try:
            events = google.upcoming(connection)
        except GoogleAuthError, RequestException, InvalidToken, ValueError, KeyError:
            messages.error(
                request,
                "Calendar could not be loaded. "
                "Try again or disconnect and reconnect Google Calendar.",
            )
    return render(
        request,
        "integrations/index.html",
        {
            "connection": connection,
            "events": events,
            "calendar_configured": google.configured(),
        },
    )


@login_required
@require_POST
@sensitive_variables()
def connect(request):
    if not google.configured():
        messages.error(request, "Google Calendar is not configured yet.")
        return redirect("integrations:index")
    oauth = google.flow()
    url, state = oauth.authorization_url(access_type="offline", prompt="consent")
    request.session["calendar_oauth"] = {
        "state": state,
        "verifier": oauth.code_verifier,
        "user": str(request.user.pk),
        "created": time.time(),
    }
    return redirect(url)


@login_required
@never_cache
@sensitive_variables()
def callback(request):
    pending = request.session.pop("calendar_oauth", None)
    if (
        not pending
        or not secrets.compare_digest(pending["state"], request.GET.get("state", ""))
        or pending["user"] != str(request.user.pk)
        or time.time() - pending["created"] > OAUTH_MAX_AGE
    ):
        messages.error(
            request,
            "Calendar connection expired or could not be verified. Please try again.",
        )
        return redirect("integrations:index")
    if request.GET.get("error") or not request.GET.get("code"):
        messages.info(request, "Google Calendar was not connected.")
        return redirect("integrations:index")
    try:
        oauth = google.flow(state=pending["state"], code_verifier=pending["verifier"])
        oauth.fetch_token(code=request.GET["code"], timeout=15)
        if google.SCOPE not in (
            oauth.credentials.granted_scopes or oauth.credentials.scopes or []
        ):
            raise ValueError("Calendar permission was not granted.")
        if not oauth.credentials.refresh_token:
            raise ValueError("Offline access was not granted. Reconnect Calendar.")
        connection, _ = GoogleCalendarConnection.objects.get_or_create(
            user=request.user
        )
        google.save_credentials(connection, oauth.credentials)
    except OAuth2Error, GoogleAuthError, RequestException, ValueError:
        messages.error(
            request,
            "Google Calendar could not be connected. "
            "Please try again and grant Calendar access.",
        )
    else:
        messages.success(request, "Google Calendar connected.")
    return redirect("integrations:index")


@login_required
@require_POST
def disconnect(request):
    GoogleCalendarConnection.objects.filter(user=request.user).delete()
    request.session.pop("calendar_oauth", None)
    messages.success(request, "Calendar disconnected and saved credentials removed.")
    return redirect("integrations:index")
