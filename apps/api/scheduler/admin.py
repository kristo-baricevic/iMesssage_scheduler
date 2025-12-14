from django.contrib import admin
from .models import ScheduledMessage, MessageStatusEvent, DeliveryThrottle


class MessageStatusEventInline(admin.TabularInline):
    model = MessageStatusEvent
    extra = 0
    readonly_fields = ("status", "timestamp", "detail")
    can_delete = False


@admin.register(ScheduledMessage)
class ScheduledMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "to_handle",
        "status",
        "scheduled_for",
        "created_at",
        "claimed_by",
        "claimed_at",
        "attempt_count",
    )
    list_filter = ("status",)
    search_fields = ("to_handle", "body", "id")
    readonly_fields = ("created_at", "updated_at")
    inlines = [MessageStatusEventInline]
    ordering = ("created_at",)


@admin.register(MessageStatusEvent)
class MessageStatusEventAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "status", "timestamp")
    list_filter = ("status",)
    search_fields = ("message__id", "message__to_handle")
    ordering = ("-timestamp",)


@admin.register(DeliveryThrottle)
class DeliveryThrottleAdmin(admin.ModelAdmin):
    list_display = ("id", "next_send_at", "interval_seconds")
