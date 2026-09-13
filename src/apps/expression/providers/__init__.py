"""Provider adapters — sync-time only.

Nothing here is imported by the running application. ``manage.py
sync_expression_catalog`` is the only caller: it fetches from each provider, normalizes
the result, and writes it into ``apps/expression/catalog/`` (checked into the repo). At
request time, ``apps/expression/services.py`` only ever reads that bundled catalog — so
a provider being slow, rate-limited or down can never affect a researcher using the app,
and CI never depends on a live external API.

This is the one place that ever knows which provider is which; everything downstream
(``services.py``, the API, the frontend) sees only the normalized shape from
``normalize.py``.
"""
