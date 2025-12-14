from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import GatewayClaimAPIView, GatewayReportAPIView, ScheduledMessageViewSet

router = DefaultRouter()
router.register(r"messages", ScheduledMessageViewSet, basename="messages")

urlpatterns = [
    path("", include(router.urls)),
    path("gateway/claim/", GatewayClaimAPIView.as_view(), name="gateway-claim"),
    path("gateway/report/", GatewayReportAPIView.as_view(), name="gateway-report"),
]
