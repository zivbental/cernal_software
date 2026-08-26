"""Root URL configuration.

Route order matters: /admin/, /api/, /static/ and /media/ are claimed first, then a
catch-all hands every remaining path to the SPA so client-side routing works on a hard
refresh or a shared link (docs/architecture.md §8).
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, re_path

from api import api
from apps.web.views import spa

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Anything not claimed above belongs to the single-page app. Kept last on purpose.
urlpatterns += [re_path(r"^(?!static/).*$", spa, name="spa")]
