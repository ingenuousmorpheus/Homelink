"""
HomeLink app server.
Serves the built app (dist/) on port 8080 with no-cache headers on
index.html, so phones always pick up the newest version after a rebuild
(hashed asset files remain cacheable).
"""

import os
import posixpath
import urllib.parse
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = int(os.getenv("PORT", "8080"))
ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist")
GUARD_UPDATE = os.path.join(ROOT, "redkryptonite-setup")


# The guard-update directory is world-readable to anyone who can reach this
# port (LAN + tailnet). It also holds `redkryptonite_lana_token.txt`, which
# grants shell and input control over that machine -- install_lana_arm.ps1
# downloads it to bootstrap a new node. Serving a credential permanently so a
# once-per-machine install can fetch it is the wrong trade, so it is refused by
# default. To run an install, start this server with
# HOMELINK_ALLOW_TOKEN_FETCH=1 and drop it again afterwards.
ALLOW_TOKEN_FETCH = os.getenv("HOMELINK_ALLOW_TOKEN_FETCH", "0") == "1"
_SECRET_NAMES = ("token", "secret", "password", "credential", ".env")


def _is_secret(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in _SECRET_NAMES)


class AppHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        if path == "/guard-update":
            path = "/guard-update/"
        if path.startswith("/guard-update/"):
            rel = path.split("?", 1)[0].split("#", 1)[0][len("/guard-update/"):]
            rel = posixpath.normpath(urllib.parse.unquote(rel)).lstrip("/")
            parts = [p for p in rel.split("/") if p and p not in (os.curdir, os.pardir)]
            if parts and _is_secret(parts[-1]) and not ALLOW_TOKEN_FETCH:
                # Resolve to a path that cannot exist, so the handler 404s
                # exactly as it would for any other missing file.
                return os.path.join(GUARD_UPDATE, "__refused_secret__")
            return os.path.join(GUARD_UPDATE, *parts)
        return super().translate_path(path)

    def list_directory(self, path):
        # Directory listings would otherwise advertise the secret by name.
        self.send_error(404, "No permission to list directory")
        return None

    def end_headers(self):
        # hashed assets (dist/assets/*) are immutable; everything else
        # (index.html and friends) must be revalidated every load
        if "/assets/" in self.path:
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()


if __name__ == "__main__":
    handler = partial(AppHandler, directory=DIST)
    print(f"HomeLink app serving on http://0.0.0.0:{PORT} (from {DIST})")
    HTTPServer(("0.0.0.0", PORT), handler).serve_forever()
