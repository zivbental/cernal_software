"""Serving the single-page app.

The React build is a static asset like any other; this view exists only so that
client-side routes survive a hard refresh or a shared link. Everything the SPA needs at
runtime comes from ``/api/`` (docs/architecture.md §8, ADR 0003).
"""

from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import never_cache

_MISSING = """<!doctype html>
<html><head><meta charset="utf-8"><title>CERNAL — frontend not built</title></head>
<body style="font-family:system-ui;max-width:38rem;margin:4rem auto;line-height:1.6">
<h1>Frontend not built</h1>
<p>The React build is missing from <code>src/static/app/</code>. Build it with:</p>
<pre style="background:#f4f4f5;padding:1rem;border-radius:.5rem">./do build-frontend</pre>
<p>The API and admin are unaffected:
<a href="/admin/">/admin/</a> &middot; <a href="/api/docs">/api/docs</a></p>
</body></html>
"""


def _index_path() -> Path:
    return Path(settings.BASE_DIR) / "src" / "static" / "app" / "index.html"


@never_cache
def spa(request, *args, **kwargs) -> HttpResponse:
    """Return the SPA shell, or a build hint when it has not been built yet."""
    index = _index_path()
    if not index.is_file():
        return HttpResponse(_MISSING, status=503)
    return HttpResponse(index.read_text(encoding="utf-8"))
