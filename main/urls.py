from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from main.views import FrontendAppView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("detector.urls")),
    path("api/", include("results.urls")),
    re_path(r"^(?!api/|admin/|media/|static/).*$", FrontendAppView.as_view(), name="frontend"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
