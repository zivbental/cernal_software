"""Root URL configuration.

Route order matters: /admin/, /api/, /static/ and /media/ are claimed first, then a
catch-all hands every remaining path to the SPA so client-side routing works on a hard
refresh or a shared link (docs/architecture.md §8).
"""

from django.contrib import admin
from django.urls import path, re_path

from api import api
from apps.web.views import spa

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
]


# Anything not claimed above belongs to the single-page app. Kept last on purpose.
urlpatterns += [re_path(r"^(?!static/|media/).*$", spa, name="spa")]
