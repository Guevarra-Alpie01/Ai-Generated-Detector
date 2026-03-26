from django.urls import path
from rest_framework.routers import DefaultRouter

from results.views import DetectionResultViewSet, ResetDetectionHistoryAPIView


router = DefaultRouter()
router.register("results", DetectionResultViewSet, basename="results")

urlpatterns = [
    path("results/reset/", ResetDetectionHistoryAPIView.as_view(), name="results-reset"),
]
urlpatterns += router.urls
