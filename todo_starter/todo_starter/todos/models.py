import uuid

from django.conf import settings
from django.db import models


class Todo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=300)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return self.title


class ImportReceipt(models.Model):
    """Keep receipts after todo deletion so retries cannot resurrect a deleted todo."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    local_id = models.UUIDField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "local_id"], name="unique_local_import"
            )
        ]

    def __str__(self):
        return f"{self.user_id}:{self.local_id}"
