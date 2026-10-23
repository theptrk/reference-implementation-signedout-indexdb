from django.conf import settings
from django.db import models


class GoogleCalendarConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    encrypted_credentials = models.TextField()
    connected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Google Calendar for user {self.user_id}"
