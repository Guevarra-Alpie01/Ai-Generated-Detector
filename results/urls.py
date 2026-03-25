from rest_framework.routers import DefaultRouter

from results.views import DetectionResultViewSet


router = DefaultRouter()
router.register("results", DetectionResultViewSet, basename="results")

urlpatterns = router.urls
