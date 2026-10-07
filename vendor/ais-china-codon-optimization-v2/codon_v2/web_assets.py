"""Explicit public presentation files shared by the local and WSGI adapters."""

WEB_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/presentation.js": ("presentation.js", "text/javascript; charset=utf-8"),
    "/presentation.css": ("presentation.css", "text/css; charset=utf-8"),
}

PUBLIC_ASSETS = {
    "codon-hero.webm": "video/webm",
    "codon-hero-poster.webp": "image/webp",
    "lower-biotech-background.png": "image/png",
    "manrope-latin-variable.woff2": "font/woff2",
    "Manrope-OFL.txt": "text/plain; charset=utf-8",
    "V1-LICENSE.txt": "text/plain; charset=utf-8",
    "NOTICE.txt": "text/plain; charset=utf-8",
}
