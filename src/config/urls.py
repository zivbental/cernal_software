"""Root URL configuration.

Route order matters: /admin/, /api/ and /static/ are claimed before the SPA catch-all
that Step 4 will add for client-side routing (docs/software-design.md §8).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Step 1 replaces this placeholder with the django-ninja API (docs §7).
    path(
        "api/health",
        lambda _request: JsonResponse({"status": "ok"}),
        name="health",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
