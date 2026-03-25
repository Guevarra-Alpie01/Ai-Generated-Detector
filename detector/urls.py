from django.urls import path

from detector.views import URLDetectionAPIView, UploadDetectionAPIView


urlpatterns = [
    path("detect/upload/", UploadDetectionAPIView.as_view(), name="detect-upload"),
    path("detect/url/", URLDetectionAPIView.as_view(), name="detect-url"),
]
