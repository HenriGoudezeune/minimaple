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
from urllib.parse import parse_qs, urlparse

from ..sessions import SessionManager, commands, help_for
from .. import mwfile
from .examples import EXAMPLES

STATIC = Path(__file__).parent / "static"
HOST = "127.0.0.1"   # bewust niet configureerbaar: alleen lokaal
MAX_BODY = 200_000
_SIGS = None
def _sigs(names):
    """Korte hint per commando: eerste regel van de docstring (max 60 tekens)."""
    global _SIGS
    if _SIGS is None:
        from .. import values
        _SIGS = {}
        for n in names:
            d = (getattr(values.BUILTINS.get(n), "__doc__", None) or "").strip().split("\n")[0]
            if d:
                _SIGS[n] = d[:60]
    return _SIGS
MAX_UPLOAD = mwfile.MAX_BYTES
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

    def _download(self, name):
        """Stuurt een bestand uit MINIMAPLE_DOWNLOADS in stukken (geen 100 MB in het geheugen)."""
        d = os.environ.get("MINIMAPLE_DOWNLOADS") or os.path.join(os.getcwd(), "downloads")
        if not d or "/" in name or name.startswith("."):
            return self._send(404, b"not found", "text/plain")
        f = Path(d) / name
        if not f.is_file():
            return self._send(404, b"not found", "text/plain")
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(f.stat().st_size))
        self.send_header("Content-Disposition", f'attachment; filename="{f.name}"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        with open(f, "rb") as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break

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
        if path in ("/download", "/download/"):
            return self._send(200, (STATIC / "download.html").read_bytes(), "text/html; charset=utf-8")
        if path.startswith("/download/"):
            return self._download(path[len("/download/"):])
        if path == "/api/examples":
            return self._json(EXAMPLES)
        if path == "/api/commands":
            b, pk = commands()
            return self._json({"builtins": b, "packages": pk, "sigs": _sigs(b)})
        if path == "/api/help":
            q = parse_qs(urlparse(self.path).query)
            name = (q.get("name") or [""])[0].strip().lstrip("?").strip()[:80]
            if not name:
                b, pk = commands()
                txt = "Commands: " + ", ".join(b) + "".join(f"\n\n{p}: " + ", ".join(ns) for p, ns in sorted(pk.items()))
                return self._json({"name": "", "found": True, "text": txt})
            h = help_for(name)
            if h is None:
                return self._json({"name": name, "found": False,
                                   "text": f"No help for '{name}'. Help > Alle commando's lists what exists."})
            return self._json({"name": name, "found": True, "text": h})
        if path.startswith("/static/"):
            f = (STATIC / path[len("/static/"):]).resolve()
            if STATIC.resolve() in f.parents and f.is_file():
                ct = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
                if f.suffix == ".webmanifest": ct = "application/manifest+json"
                return self._send(200, f.read_bytes(), ct, {"Cache-Control": "no-cache"})
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, b"forbidden", "text/plain")
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self._send(403, b"forbidden", "text/plain")
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"error": "bad length"}, 400)
        path = urlparse(self.path).path
        if path == "/api/open":
            # upload van een werkblad: enkel parsen in het geheugen, niets op schijf
            if n > MAX_UPLOAD:
                return self._json({"error": "File too large (max 5 MB)."}, 413)
            if not _rate_ok(self._client_ip()):
                return self._json({"error": "Too many requests, try again in a minute."}, 429)
            name = (parse_qs(urlparse(self.path).query).get("name") or [""])[0][:200]
            try:
                res = mwfile.parse_file(name, self.rfile.read(n))
            except mwfile.WorksheetError as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:  # nooit een stacktrace naar de client
                return self._json({"error": f"Could not read file ({type(e).__name__})."}, 400)
            return self._json({"name": name, **res})
        if n > MAX_BODY:
            return self._json({"error": "too large"}, 413)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        sid, _ = self._sid()
        if path == "/api/eval":
            code = str(data.get("code", ""))
            if not _rate_ok(self._client_ip()):
                return self._json({"error": "Too many requests, try again in a minute."}, 429)
            try:
                res = MGR.eval(code, sid)
            except Exception:   # bv. proces gedood via /api/stop terwijl het rekende
                res = [{"stmt": code, "show": True, "text": "", "latex": None, "plots": [],
                        "error": "Interrupted; session reset, earlier definitions lost."}]
            out = []
            for r in res:
                r = dict(r)
                r["plots"] = ["data:image/png;base64," + base64.b64encode(p).decode() for p in r.get("plots") or []]
                out.append(r)
            return self._json({"results": out})
        if path in ("/api/reset", "/api/stop"):   # stop = rekenproces doden (sessie gaat verloren)
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
