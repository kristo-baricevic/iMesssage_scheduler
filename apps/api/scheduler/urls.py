from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import GatewayClaimAPIView, GatewayReportAPIView, HealthAPIView, ScheduledMessageViewSet

router = DefaultRouter()
router.register(r"messages", ScheduledMessageViewSet, basename="messages")

urlpatterns = [
    path("", include(router.urls)),
    path("health/", HealthAPIView.as_view()),
    path("gateway/claim/", GatewayClaimAPIView.as_view()),
    path("gateway/report/", GatewayReportAPIView.as_view()),
]
