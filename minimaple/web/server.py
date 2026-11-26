"""mini-Maple webnotebook. Alleen stdlib. `python -m minimaple.web` (127.0.0.1:8750, poort via MINIMAPLE_PORT)."""
import base64
import json
import time
import mimetypes
import os
import secrets
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..sessions import SessionManager, commands
from .examples import EXAMPLES

STATIC = Path(__file__).parent / "static"
HOST = "127.0.0.1"   # bewust niet configureerbaar: alleen lokaal
MAX_BODY = 200_000
_HITS = {}
def _rate_ok(ip, limit=int(os.environ.get("MINIMAPLE_RATE", "60")), window=60):
    now = time.time()
    q = [t for t in _HITS.get(ip, []) if now - t < window]
    if len(q) >= limit:
        _HITS[ip] = q
        return False
    q.append(now); _HITS[ip] = q
    if len(_HITS) > 5000:
        _HITS.clear()
    return True
MGR = SessionManager()


class Handler(BaseHTTPRequestHandler):
    server_version = "minimaple"

    def log_message(self, *a):
        pass

    # --- helpers
    def _sid(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        if "mm_sid" in c and c["mm_sid"].value.isalnum():
            return c["mm_sid"].value, False
        return secrets.token_hex(8), True

    def _send(self, code, body, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200, extra=None):
        self._send(code, json.dumps(obj).encode(), "application/json; charset=utf-8", extra)

    def _host_ok(self):
        h = (self.headers.get("Host") or "").split(":")[0]
        extra = [x for x in os.environ.get("MINIMAPLE_HOSTS", "").split(",") if x]
        return h in ("127.0.0.1", "localhost", "[::1]", *extra)

    def _client_ip(self):
        return (self.headers.get("X-Real-IP") or self.client_address[0])

    # --- routes
    def do_GET(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        path = urlparse(self.path).path
        if path == "/":
            sid, new = self._sid()
            extra = {"Set-Cookie": f"mm_sid={sid}; Path=/; HttpOnly; SameSite=Strict"} if new else {}
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8", extra)
        if path == "/api/examples":
            return self._json(EXAMPLES)
        if path == "/api/commands":
            b, pk = commands()
            return self._json({"builtins": b, "packages": pk})
        if path.startswith("/static/"):
            f = (STATIC / path[len("/static/"):]).resolve()
            if STATIC.resolve() in f.parents and f.is_file():
                ct = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                if f.suffix == ".webmanifest": ct = "application/manifest+json"
                return self._send(200, f.read_bytes(), ct, {"Cache-Control": "public, max-age=3600"})
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self._send(403, b"forbidden", "text/plain")
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return self._json({"error": "too large"}, 413)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        sid, _ = self._sid()
        path = urlparse(self.path).path
        if path == "/api/eval":
            code = str(data.get("code", ""))
            if not _rate_ok(self._client_ip()):
                return self._json({"error": "Too many requests, try again in a minute."}, 429)
            res = MGR.eval(code, sid)
            out = []
            for r in res:
                r = dict(r)
                r["plots"] = ["data:image/png;base64," + base64.b64encode(p).decode() for p in r.get("plots") or []]
                out.append(r)
            return self._json({"results": out})
        if path == "/api/reset":
            MGR.reset(sid)
            return self._json({"ok": True})
        self._send(404, b"not found", "text/plain")


def main():
    port = int(os.environ.get("MINIMAPLE_PORT", "8750"))
    srv = ThreadingHTTPServer((HOST, port), Handler)
    print(f"mini-Maple op http://{HOST}:{port}", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        MGR.close()
