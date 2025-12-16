import uuid
from django.db import models
from django.utils import timezone


class MessageStatus(models.TextChoices):
    QUEUED = "QUEUED"
    ACCEPTED = "ACCEPTED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    RECEIVED = "RECEIVED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class ScheduledMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    to_handle = models.CharField(max_length=255)
    body = models.TextField()

    scheduled_for = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=MessageStatus.choices,
        default=MessageStatus.QUEUED,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    claimed_at = models.DateTimeField(null=True, blank=True)
    claimed_by = models.CharField(max_length=128, null=True, blank=True)

    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "scheduled_for", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.to_handle} [{self.status}]"


class MessageStatusEvent(models.Model):
    id = models.BigAutoField(primary_key=True)

    message = models.ForeignKey(
        ScheduledMessage,
        on_delete=models.CASCADE,
        related_name="events",
    )
    status = models.CharField(max_length=16, choices=MessageStatus.choices)
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    detail = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["timestamp"]

    def __str__(self) -> str:
        return f"{self.message_id} -> {self.status}"


class DeliveryThrottle(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    next_send_at = models.DateTimeField(default=timezone.now)
    interval_seconds = models.PositiveIntegerField(default=3600)

    max_attempts = models.PositiveSmallIntegerField(default=5)
    retry_base_seconds = models.PositiveIntegerField(default=60)
    retry_max_seconds = models.PositiveIntegerField(default=21600)

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls) -> "DeliveryThrottle":
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    def __str__(self) -> str:
        return (
            "Throttle("
            f"next_send_at={self.next_send_at}, "
            f"interval_seconds={self.interval_seconds}, "
            f"max_attempts={self.max_attempts}, "
            f"retry_base_seconds={self.retry_base_seconds}, "
            f"retry_max_seconds={self.retry_max_seconds}"
            ")"
        )
