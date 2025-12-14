from django.shortcuts import render

from typing import Any

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MessageStatus, MessageStatusEvent, ScheduledMessage
from .serializers import ScheduledMessageCreateSerializer, ScheduledMessageSerializer
from .services import claim_next_message


class ScheduledMessageViewSet(viewsets.ModelViewSet):
    queryset = ScheduledMessage.objects.all().order_by("-created_at")
    serializer_class = ScheduledMessageSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return ScheduledMessageCreateSerializer
        return ScheduledMessageSerializer

    def create(self, request, *args, **kwargs):
        create_serializer = self.get_serializer(data=request.data)
        create_serializer.is_valid(raise_exception=True)
        msg = create_serializer.save()

        out_serializer = ScheduledMessageSerializer(msg, context=self.get_serializer_context())
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)

    def get_queryset(self):
        qs = super().get_queryset()

        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        scheduled_from = self.request.query_params.get("scheduled_from")
        if scheduled_from:
            qs = qs.filter(scheduled_for__gte=scheduled_from)

        scheduled_to = self.request.query_params.get("scheduled_to")
        if scheduled_to:
            qs = qs.filter(scheduled_for__lte=scheduled_to)

        to_handle = self.request.query_params.get("to_handle")
        if to_handle:
            qs = qs.filter(to_handle__icontains=to_handle)

        return qs

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        msg = self.get_object()
        if msg.status in {MessageStatus.SENT, MessageStatus.DELIVERED, MessageStatus.RECEIVED}:
            return Response(
                {"detail": "Cannot cancel a message that has already been sent."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        msg.status = MessageStatus.CANCELED
        msg.save(update_fields=["status", "updated_at"])

        MessageStatusEvent.objects.create(
            message=msg,
            status=MessageStatus.CANCELED,
            detail={"source": "api"},
        )

        return Response(ScheduledMessageSerializer(msg).data, status=status.HTTP_200_OK)


class GatewayClaimAPIView(APIView):
    def post(self, request):
        gateway_id = request.data.get("gateway_id")
        if not gateway_id:
            return Response({"detail": "gateway_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        claimed = claim_next_message(gateway_id=gateway_id)
        if not claimed:
            return Response(status=status.HTTP_204_NO_CONTENT)

        return Response(
            {
                "id": claimed.id,
                "to_handle": claimed.to_handle,
                "body": claimed.body,
                "scheduled_for": claimed.scheduled_for,
            },
            status=status.HTTP_200_OK,
        )


class GatewayReportAPIView(APIView):
    def post(self, request):
        message_id = request.data.get("message_id")
        new_status = request.data.get("status")
        error = request.data.get("error")
        detail = request.data.get("detail")

        if not message_id or not new_status:
            return Response(
                {"detail": "message_id and status are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        allowed = {
            MessageStatus.SENT,
            MessageStatus.DELIVERED,
            MessageStatus.RECEIVED,
            MessageStatus.FAILED,
        }
        if new_status not in allowed:
            return Response(
                {"detail": f"status must be one of: {sorted(list(allowed))}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            msg = ScheduledMessage.objects.get(id=message_id)
        except ScheduledMessage.DoesNotExist:
            return Response({"detail": "message not found"}, status=status.HTTP_404_NOT_FOUND)

        update_fields: list[str] = ["status", "updated_at"]
        msg.status = new_status

        if new_status == MessageStatus.FAILED:
            msg.attempt_count = (msg.attempt_count or 0) + 1
            msg.last_error = error or "unknown error"
            update_fields += ["attempt_count", "last_error"]
        else:
            if msg.last_error:
                msg.last_error = None
                update_fields.append("last_error")

        msg.save(update_fields=update_fields)

        MessageStatusEvent.objects.create(
            message=msg,
            status=new_status,
            detail={
                "reported_at": timezone.now().isoformat(),
                "error": error,
                "detail": detail,
            },
        )

        return Response(ScheduledMessageSerializer(msg).data, status=status.HTTP_200_OK)
