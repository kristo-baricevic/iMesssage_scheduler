from rest_framework import serializers

from .models import MessageStatus, MessageStatusEvent, ScheduledMessage


class MessageStatusEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageStatusEvent
        fields = ["id", "status", "timestamp", "detail"]


class ScheduledMessageSerializer(serializers.ModelSerializer):
    events = MessageStatusEventSerializer(many=True, read_only=True)

    class Meta:
        model = ScheduledMessage
        fields = [
            "id",
            "to_handle",
            "body",
            "scheduled_for",
            "status",
            "created_at",
            "updated_at",
            "claimed_at",
            "claimed_by",
            "attempt_count",
            "last_error",
            "events",
        ]
        read_only_fields = [
            "id",
            "status",
            "created_at",
            "updated_at",
            "claimed_at",
            "claimed_by",
            "attempt_count",
            "last_error",
            "events",
        ]


class ScheduledMessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduledMessage
        fields = ["to_handle", "body", "scheduled_for"]

    def create(self, validated_data):
        msg = ScheduledMessage.objects.create(
            **validated_data,
            status=MessageStatus.QUEUED,
        )
        MessageStatusEvent.objects.create(
            message=msg,
            status=MessageStatus.QUEUED,
            detail={"source": "api"},
        )
        return msg
