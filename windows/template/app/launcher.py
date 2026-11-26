"""mini-Maple launcher (offline) voor Windows, macOS en Linux.

Start de webserver van minimaple op 127.0.0.1, opent de UI in een app-venster van
Edge/Chrome/Chromium/Brave (fallback: de standaardbrowser) en stopt de server
zodra dat venster dicht is (bij de standaardbrowser: als het tabblad geen
hartslag meer stuurt).

Gebruik:  python launcher.py [BESTAND.mw|BESTAND.mpl|minimaple://open#ws=...]

Bestandsargument (toekomstbestendig, de UI heeft nog geen open-functie):
  De launcher registreert het bestand en opent  /?open=<token>.
  De UI kan het daarna ophalen met  GET /api/launcher/file?token=<token>
  -> {"name": ..., "path": ..., "ext": ..., "content": <tekst>}  (404 als onbekend).
  Een tweede launch (server draait al) registreert het bestand bij de lopende
  server via POST /api/launcher/register (met geheim uit de lockfile).
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

def _appdir():
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "mini-Maple"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "mini-Maple"
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "mini-Maple"


APPDIR = _appdir()
LOCK = APPDIR / "instance.json"
LOG = APPDIR / "launcher.log"
PREFERRED_PORTS = range(18750, 18760)   # vaste poort => localStorage (historiek) blijft bewaard
IDLE_LIMIT = 10 * 60                    # fallback-modus: stop na 10 min zonder verkeer of hartslag
# In elke HTML-pagina: hartslag, zodat de server in de fallback-modus weet dat het tabblad nog open is.
HEARTBEAT = (b'<script>setInterval(function(){fetch("/api/launcher/ping",{cache:"no-store"})'
             b'.catch(function(){})},60000)</script>')
MAX_FILE = 2_000_000


def log(*a):
    try:
        APPDIR.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + " ".join(map(str, a)) + "\n")
    except OSError:
        pass


def _read_lock():
    try:
        return json.loads(LOCK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _alive(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/launcher/ping", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _register_remote(info, path):
    """Registreer een bestand bij een al draaiende server; geeft token of None."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}/api/launcher/register",
        data=json.dumps({"secret": info["secret"], "path": path}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read()).get("token")
    except Exception as e:
        log("register mislukt:", e)
        return None


def _find_browser():
    """Chromium-achtige browser die --app kent, of None."""
    if os.name == "nt":
        roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        cands = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe",
                 r"BraveSoftware\Brave-Browser\Application\brave.exe"]
        for c in cands:
            for r in roots:
                if r and Path(r, c).is_file():
                    return str(Path(r, c))
        return None
    if sys.platform == "darwin":
        apps = ["Google Chrome", "Microsoft Edge", "Chromium", "Brave Browser", "Vivaldi"]
        for root in (Path("/Applications"), Path.home() / "Applications"):
            for a in apps:
                exe = root / f"{a}.app" / "Contents" / "MacOS" / a
                if exe.is_file():
                    return str(exe)
        return None
    import shutil
    for c in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
              "microsoft-edge-stable", "brave-browser", "vivaldi-stable"):
        exe = shutil.which(c)
        if exe:
            return exe
    return None


def _profile_dir(exe):
    # Snap-browsers (Ubuntu) mogen niet in verborgen mappen schrijven.
    if exe.startswith("/snap/"):
        name = Path(exe).name.split(".")[0]
        return Path.home() / "snap" / name / "common" / "mini-Maple-profiel"
    return APPDIR / "browser-profiel"


def _open_window(url, wait):
    """Open een app-venster. wait=True: geeft het Popen-object terug (eigen profiel)."""
    exe = _find_browser()
    if exe:
        args = [exe, f"--app={url}", f"--user-data-dir={_profile_dir(exe)}",
                "--no-first-run", "--no-default-browser-check", "--window-size=1200,860"]
        try:
            return subprocess.Popen(args)
        except OSError as e:
            log("browser start mislukt:", e)
    webbrowser.open(url)
    return None


def _register_protocol():
    """minimaple:// koppelen aan deze app (HKCU, geen admin), zodat 'Openen in app' in de webversie werkt."""
    if os.name != "nt":
        return
    try:
        import winreg
        vbs = Path(__file__).resolve().parent.parent / "mini-Maple.vbs"
        wscript = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"
        cmd = f'"{wscript}" "{vbs}" "%1"'
        base = r"Software\Classes\minimaple"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:mini-Maple")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
    except Exception as e:
        log("protocol registreren mislukt:", e)


def _integrate_appimage():
    """AppImage: .desktop-bestand, MIME-types en icoon in ~/.local/share zetten (zoals bij de .deb),
    zodat 'Openen met' en minimaple:// werken. Wordt elke start bijgewerkt (pad kan veranderen)."""
    img = os.environ.get("APPIMAGE")
    if sys.platform != "linux" or not img or os.environ.get("MINIMAPLE_NO_INTEGRATE"):
        return
    try:
        import shutil
        here = Path(__file__).resolve().parent
        share = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        desk = (here / "mini-maple.desktop").read_text(encoding="utf-8")
        desk = desk.replace("Exec=mini-maple %u", f'Exec="{img}" %u')
        target = share / "applications" / "mini-maple.desktop"
        icon = share / "icons" / "hicolor" / "256x256" / "apps" / "mini-maple.png"
        mime = share / "mime" / "packages" / "mini-maple.xml"
        if target.is_file() and target.read_text(encoding="utf-8") == desk and icon.is_file() and mime.is_file():
            return
        for f in (target, icon, mime):
            f.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(desk, encoding="utf-8")
        shutil.copyfile(here / "mini-maple.png", icon)
        shutil.copyfile(here / "mini-maple.xml", mime)
        for cmd in (["update-mime-database", str(share / "mime")],
                    ["update-desktop-database", str(share / "applications")],
                    ["xdg-mime", "default", "mini-maple.desktop", "x-scheme-handler/minimaple"]):
            if shutil.which(cmd[0]):
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        log("AppImage geïntegreerd:", target)
    except Exception as e:
        log("AppImage-integratie mislukt:", e)


def main():
    APPDIR.mkdir(parents=True, exist_ok=True)
    _register_protocol()
    _integrate_appimage()
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    frag = ""
    if arg and arg.lower().startswith("minimaple:"):
        # minimaple://open#ws=... (vanuit de webversie): werkblad meegeven via het URL-fragment
        frag = arg.split("#", 1)[1] if "#" in arg else ""
        frag = "".join(c for c in frag if c.isalnum() or c in "-_=.~")[:200_000]
        frag = "#" + frag if frag else ""
        arg = None
    if arg and arg.lower().startswith("file://"):
        from urllib.parse import unquote
        arg = unquote(urlparse(arg).path)
    if arg:
        arg = str(Path(arg).resolve())

    # Al een server actief? Dan enkel een extra venster openen.
    info = _read_lock()
    if info and _alive(info.get("port")):
        url = f"http://127.0.0.1:{info['port']}/"
        if arg:
            tok = _register_remote(info, arg)
            if tok:
                url += f"?open={tok}"
        _open_window(url + frag, wait=False)
        return

    # Server starten (in dit proces).
    os.environ.setdefault("MINIMAPLE_RATE", "100000")   # lokaal: geen rate limit nodig
    from minimaple.web import server as S

    last = [time.time()]
    files = {}
    secret = secrets.token_hex(16)

    def register(path):
        p = Path(path)
        if not p.is_file():
            return None
        tok = secrets.token_hex(8)
        files[tok] = p
        return tok

    class Handler(S.Handler):
        def _send(self, code, body, ctype, extra=None):
            if ctype.startswith("text/html") and b"</body>" in body:
                body = body.replace(b"</body>", HEARTBEAT + b"</body>", 1)
            return super()._send(code, body, ctype, extra)

        def do_GET(self):
            last[0] = time.time()
            u = urlparse(self.path)
            if u.path == "/api/launcher/ping":
                return self._json({"ok": True, "app": "mini-Maple"})
            if u.path == "/api/launcher/file":
                if not self._host_ok():
                    return self._send(403, b"forbidden", "text/plain")
                tok = (parse_qs(u.query).get("token") or [""])[0]
                p = files.get(tok)
                if p is None or not p.is_file() or p.stat().st_size > MAX_FILE:
                    return self._json({"error": "not found"}, 404)
                raw = p.read_bytes()
                for enc in ("utf-8-sig", "cp1252"):
                    try:
                        txt = raw.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                return self._json({"name": p.name, "path": str(p), "ext": p.suffix.lower(), "content": txt})
            return super().do_GET()

        def do_POST(self):
            last[0] = time.time()
            if urlparse(self.path).path == "/api/launcher/register":
                if self.headers.get("Origin"):
                    return self._send(403, b"forbidden", "text/plain")
                n = min(int(self.headers.get("Content-Length") or 0), 100_000)
                try:
                    d = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._json({"error": "bad json"}, 400)
                if not secrets.compare_digest(str(d.get("secret", "")), secret):
                    return self._send(403, b"forbidden", "text/plain")
                tok = register(str(d.get("path", "")))
                return self._json({"token": tok}, 200 if tok else 404)
            return super().do_POST()

    class Server(ThreadingHTTPServer):
        allow_reuse_address = False          # Windows: anders kan een bezette poort 'gedeeld' worden
        daemon_threads = True

        def server_bind(self):
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    srv = None
    for port in [*PREFERRED_PORTS, 0]:
        try:
            srv = Server((S.HOST, port), Handler)
            break
        except OSError:
            continue
    port = srv.server_address[1]
    os.environ["MINIMAPLE_PORT"] = str(port)
    LOCK.write_text(json.dumps({"port": port, "secret": secret, "pid": os.getpid()}), encoding="utf-8")
    log("server op poort", port)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    url = f"http://127.0.0.1:{port}/"
    if arg:
        tok = register(arg)
        if tok:
            url += f"?open={tok}"

    try:
        t0 = time.time()
        proc = _open_window(url + frag, wait=True)
        if proc is not None:
            proc.wait()
            if time.time() - t0 < 5:
                # browser gaf het venster door aan een ander proces: val terug op idle-detectie
                log("browser stopte meteen; idle-modus")
                proc = None
        if proc is None:
            while time.time() - last[0] < IDLE_LIMIT:
                time.sleep(15)
    finally:
        log("stoppen")
        try:
            if (_read_lock() or {}).get("pid") == os.getpid():
                LOCK.unlink()
        except OSError:
            pass
        srv.shutdown()
        try:
            S.MGR.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("fout:", repr(e))
        raise
