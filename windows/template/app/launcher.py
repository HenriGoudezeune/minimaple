"""mini-Maple launcher (offline) voor Windows, macOS en Linux.

Start de webserver van minimaple op 127.0.0.1, opent de UI in een app-venster van
Edge/Chrome/Chromium/Brave (fallback: de standaardbrowser) en stopt de server
zodra dat venster dicht is (bij de standaardbrowser: als het tabblad geen
hartslag meer stuurt).

Gebruik:  python launcher.py [BESTAND.mw|BESTAND.mpl|minimaple://open#ws=...]

Draait er al een app-venster, dan gaat een bestand of minimaple://-link via de inbox naar dat
venster (nieuw tabblad); anders opent een nieuw venster.

Updates (alleen voor de UI van deze launcher, met het geheim uit <meta name="mm-token">):
  GET  /api/launcher/version  -> {"version", "kind", "asset"}
  POST /api/launcher/update   -> nieuwste release downloaden, SHA256 controleren, installeren, herstarten
  GET  /api/launcher/update   -> voortgang {"state", "done", "total", "msg", "version", "cmd"}

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
import tempfile
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


# ---------------------------------------------------------------- updates
REPO = "HenriGoudezeune/minimaple"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
UPD = {"state": "idle", "done": 0, "total": 0, "msg": "", "version": "", "cmd": ""}
QUIT = threading.Event()        # gezet door een update: launcher stopt (en wordt door een helper herstart)
BROWSER = [None]                # Popen van het app-venster


def app_version():
    try:
        from minimaple._version import __version__
        return __version__
    except Exception:
        return "0.0.0"


def _vtuple(v):
    out = []
    for p in str(v).strip().lstrip("vV").split("-")[0].split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple((out + [0, 0, 0])[:3])


def newer(a, b):
    """True als versie a nieuwer is dan b."""
    return _vtuple(a) > _vtuple(b)


def install_kind():
    """Hoe deze kopie geïnstalleerd is: bepaalt welk bestand een update nodig heeft."""
    here = Path(__file__).resolve()
    if app_version() == "0.0.0":
        return "dev"
    if os.name == "nt":
        return "win-setup" if (here.parent.parent / "unins000.exe").is_file() else "win-zip"
    if sys.platform == "darwin":
        return "mac" if here.parents[3].suffix == ".app" else "dev"
    if os.environ.get("APPIMAGE"):
        return "appimage"
    if str(here).startswith("/opt/mini-maple/"):
        return "deb"
    return "dev"


def asset_for(kind):
    import platform
    if kind == "win-setup":
        return "mini-Maple-setup.exe"
    if kind == "mac":
        return "mini-Maple-macos-%s.dmg" % ("arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64")
    if kind == "appimage":
        return "mini-Maple-x86_64.AppImage"
    if kind == "deb":
        return "mini-maple_amd64.deb"
    return None


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "mini-Maple-updater", "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _expected_sha(rel, name):
    """SHA256 uit het SHA256SUMS-asset, anders uit het 'digest'-veld van GitHub, anders None."""
    for a in rel.get("assets", []):
        if a.get("name") == "SHA256SUMS":
            try:
                with _get(a["browser_download_url"]) as r:
                    for line in r.read(200_000).decode("utf-8", "replace").splitlines():
                        parts = line.split()
                        if len(parts) == 2 and parts[1].lstrip("*") == name and len(parts[0]) == 64:
                            return parts[0].lower()
            except Exception as e:
                log("SHA256SUMS niet gelezen:", e)
    for a in rel.get("assets", []):
        d = str(a.get("digest") or "")
        if a.get("name") == name and d.startswith("sha256:"):
            return d[7:].lower()
    return None


def download_asset(rel, name, dest_dir):
    """Download een release-asset naar dest_dir en controleer grootte en SHA256. Geeft het pad."""
    import hashlib
    asset = next((a for a in rel.get("assets", []) if a.get("name") == name), None)
    if asset is None:
        raise RuntimeError(f"{name} staat niet in release {rel.get('tag_name')}")
    url = str(asset["browser_download_url"])
    if not url.startswith(f"https://github.com/{REPO}/releases/download/"):
        raise RuntimeError("onverwachte download-URL")
    size, want = int(asset.get("size") or 0), _expected_sha(rel, name)
    if not want:
        raise RuntimeError("geen controlesom (SHA256) gevonden voor " + name)
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    out = Path(dest_dir) / (name + ".part")
    h = hashlib.sha256()
    UPD.update(done=0, total=size)
    with _get(url, timeout=60) as r, open(out, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk); h.update(chunk)
            UPD["done"] += len(chunk)
    if UPD["done"] != size:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"download onvolledig ({UPD['done']} van {size} bytes)")
    if h.hexdigest() != want:
        out.unlink(missing_ok=True)
        raise RuntimeError("controlesom klopt niet: download geweigerd")
    final = Path(dest_dir) / name
    os.replace(out, final)
    return final


def _detach(args):
    """Start een helperproces dat de launcher overleeft."""
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = 0x00000200 | 0x08000000   # NEW_PROCESS_GROUP | NO_WINDOW (verborgen console, overleeft de launcher)
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(args, **kw)


def _quit_soon():
    """Sluit het app-venster en laat main() stoppen (de helper wacht op deze PID)."""
    def go():
        time.sleep(1.5)                     # de UI krijgt nog de laatste status
        QUIT.set()
        p = BROWSER[0]
        if p is not None:
            try:
                p.terminate()
            except Exception:
                pass
    threading.Thread(target=go, daemon=True).start()


def _apply(kind, path, version):
    pid = os.getpid()
    if kind == "win-setup":
        app_dir = Path(__file__).resolve().parent.parent
        wscript = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"
        cmdf = Path(path).with_name("mini-Maple-update.cmd")
        cmdf.write_text("\r\n".join([
            "@echo off",
            ":wacht",
            f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul && (ping -n 2 127.0.0.1 >nul & goto wacht)',
            f'"{path}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS '
            f'/LOG="{APPDIR / "update-setup.log"}"',
            f'start "" "{wscript}" "{app_dir / "mini-Maple.vbs"}"',
            ""]), encoding="cp1252")
        _detach(["cmd.exe", "/d", "/c", str(cmdf)])
        UPD.update(state="restarting", msg="De installer werkt mini-Maple bij en start de app daarna opnieuw.")
        _quit_soon()
    elif kind == "appimage":
        cur = Path(os.environ["APPIMAGE"])
        new = cur.with_name(cur.name + ".new")
        import shutil
        shutil.copyfile(path, new)
        os.chmod(new, 0o755)
        os.replace(new, cur)                 # de lopende versie blijft werken (open inode)
        Path(path).unlink(missing_ok=True)
        _detach(["/bin/sh", "-c", 'while kill -0 "$1" 2>/dev/null; do sleep 1; done; exec "$2"', "sh", str(pid), str(cur)])
        UPD.update(state="restarting", msg=f"Bijgewerkt naar {version}. mini-Maple start opnieuw.")
        _quit_soon()
    elif kind == "mac":
        bundle = Path(__file__).resolve().parents[3]
        if os.access(bundle.parent, os.W_OK):
            script = Path(path).with_name("mini-Maple-update.sh")
            script.write_text(r'''#!/bin/sh
# wacht tot mini-Maple gestopt is, vervang de .app door die uit de .dmg en start opnieuw
PID="$1"; DMG="$2"; APP="$3"
while kill -0 "$PID" 2>/dev/null; do sleep 1; done
MNT="$(mktemp -d /tmp/mini-Maple-dmg.XXXXXX)"
if hdiutil attach -nobrowse -readonly -noverify -mountpoint "$MNT" "$DMG" >/dev/null; then
  if [ -d "$MNT/mini-Maple.app" ] && ditto "$MNT/mini-Maple.app" "$APP.new"; then
    xattr -dr com.apple.quarantine "$APP.new" 2>/dev/null
    rm -rf "$APP.old"; mv "$APP" "$APP.old" && mv "$APP.new" "$APP" && rm -rf "$APP.old"
    [ -d "$APP" ] || mv "$APP.old" "$APP"
  fi
  hdiutil detach "$MNT" -quiet || hdiutil detach "$MNT" -force -quiet
  rm -f "$DMG"
  open "$APP"
else
  open "$DMG"
fi
''', encoding="utf-8")
            os.chmod(script, 0o755)
            _detach(["/bin/sh", str(script), str(pid), str(path), str(bundle)])
            UPD.update(state="restarting", msg=f"mini-Maple wordt bijgewerkt naar {version} en start daarna opnieuw.")
            _quit_soon()
        else:
            subprocess.Popen(["open", str(path)])
            UPD.update(state="manual", msg="De schijfkopie is geopend. Sluit mini-Maple, sleep mini-Maple naar "
                                           "Programma's en kies 'Vervang'.")
    elif kind == "deb":
        import shutil
        cmd = f"sudo apt install {path}"
        if shutil.which("pkexec") and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            UPD.update(state="installing", msg="Bevestig de installatie met je wachtwoord.")
            r = subprocess.run(["pkexec", "apt-get", "install", "-y", str(path)], stdout=subprocess.DEVNULL,
                               stderr=subprocess.PIPE, timeout=1800)
            if r.returncode == 0:
                _detach(["/bin/sh", "-c", 'while kill -0 "$1" 2>/dev/null; do sleep 1; done; exec /usr/bin/mini-maple',
                         "sh", str(pid)])
                UPD.update(state="restarting", msg=f"Bijgewerkt naar {version}. mini-Maple start opnieuw.")
                _quit_soon()
                return
            log("pkexec mislukt:", r.returncode, r.stderr[-500:])
        UPD.update(state="manual", cmd=cmd, msg="Installeer het gedownloade pakket in een terminal:")


def run_update():
    """Achtergrondthread: nieuwste release zoeken, downloaden, controleren en installeren."""
    try:
        kind = install_kind()
        name = asset_for(kind)
        if not name:
            UPD.update(state="manual", msg="Deze kopie kan zichzelf niet bijwerken: download de nieuwe versie.")
            return
        UPD.update(state="checking", msg="Nieuwste versie opzoeken…", done=0, total=0, cmd="")
        with _get(API_LATEST) as r:
            rel = json.loads(r.read(2_000_000))
        version = str(rel.get("tag_name", "")).lstrip("v")
        UPD["version"] = version
        if not newer(version, app_version()):
            UPD.update(state="uptodate", msg=f"Je hebt al de nieuwste versie ({app_version()}).")
            return
        UPD.update(state="downloading", msg=f"{name} downloaden…")
        dest = Path(tempfile.gettempdir()) / "mini-Maple-update"
        path = download_asset(rel, name, dest)
        UPD.update(state="installing", msg="Installeren…")
        _apply(kind, path, version)
    except Exception as e:
        log("update mislukt:", repr(e))
        UPD.update(state="error", msg=f"Bijwerken mislukt: {e}")


def _deliver(info, path, ws):
    """Bestand/werkblad aan een open app-venster geven (nieuw tabblad). -> (afgeleverd?, token)."""
    def call(ep, body):
        req = urllib.request.Request(f"http://127.0.0.1:{info['port']}/api/launcher/{ep}",
                                     data=json.dumps({"secret": info["secret"], **body}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    try:
        tok = call("register", {"path": path or "", "ws": ws or "", "deliver": True}).get("token")
        if not tok:
            return False, None
        for i in range(12):            # de UI haalt de inbox elke ~1,5 s op
            time.sleep(0.5)
            if call("claimed", {"token": tok, "final": i == 11}).get("claimed"):
                return True, tok
        return False, tok
    except Exception as e:
        log("afleveren mislukt:", e)
        return False, None


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
        if arg or frag:
            ok, tok = _deliver(info, arg, frag[4:] if frag.startswith("#ws=") else "")
            if ok:
                return
            if arg:
                tok = tok or _register_remote(info, arg)
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
    ui_token = secrets.token_hex(16)        # staat enkel in de HTML van deze server (same-origin)
    inbox, claimed, ilock = {}, set(), threading.Lock()
    meta = f'<meta name="mm-token" content="{ui_token}">'.encode()

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
                body = body.replace(b"</body>", HEARTBEAT + b"</body>", 1).replace(b"</head>", meta + b"</head>", 1)
            return super()._send(code, body, ctype, extra)

        def _ui_ok(self):
            """Alleen de eigen UI: juiste Host, eigen Origin (als die er is) en het geheim uit de pagina.
            De eigen header dwingt bij andere sites een CORS-preflight af, die deze server niet beantwoordt."""
            if not self._host_ok():
                return False
            o = self.headers.get("Origin")
            if o and urlparse(o).netloc != self.headers.get("Host"):
                return False
            return secrets.compare_digest(self.headers.get("X-MM-Token", ""), ui_token)

        def do_GET(self):
            last[0] = time.time()
            u = urlparse(self.path)
            if u.path == "/api/launcher/ping":
                return self._json({"ok": True, "app": "mini-Maple"})
            if u.path == "/api/launcher/version":
                if not self._host_ok():
                    return self._send(403, b"forbidden", "text/plain")
                k = install_kind()
                return self._json({"version": app_version(), "kind": k, "asset": asset_for(k)})
            if u.path in ("/api/launcher/update", "/api/launcher/inbox"):
                if not self._ui_ok():
                    return self._send(403, b"forbidden", "text/plain")
                if u.path == "/api/launcher/update":
                    return self._json(UPD)
                with ilock:
                    items = list(inbox.values()); claimed.update(inbox); inbox.clear()
                return self._json({"items": [{"token": i["token"], "ws": i["ws"]} for i in items]})
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
            path = urlparse(self.path).path
            if path == "/api/launcher/update":
                if not self._ui_ok():
                    return self._send(403, b"forbidden", "text/plain")
                if UPD["state"] in ("checking", "downloading", "installing", "restarting"):
                    return self._json(UPD, 409)
                UPD.update(state="checking", msg="", done=0, total=0, cmd="")
                threading.Thread(target=run_update, daemon=True).start()
                return self._json(UPD)
            if path == "/api/launcher/claimed":
                if self.headers.get("Origin"):
                    return self._send(403, b"forbidden", "text/plain")
                n = min(int(self.headers.get("Content-Length") or 0), 10_000)
                try:
                    d = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._json({"error": "bad json"}, 400)
                if not secrets.compare_digest(str(d.get("secret", "")), secret):
                    return self._send(403, b"forbidden", "text/plain")
                t = str(d.get("token", ""))
                with ilock:
                    ok = t in claimed
                    if not ok and d.get("final"):
                        inbox.pop(t, None)   # niet opgehaald: de tweede launcher opent zelf een venster
                return self._json({"claimed": ok})
            if path == "/api/launcher/register":
                if self.headers.get("Origin"):
                    return self._send(403, b"forbidden", "text/plain")
                n = min(int(self.headers.get("Content-Length") or 0), 100_000)
                try:
                    d = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._json({"error": "bad json"}, 400)
                if not secrets.compare_digest(str(d.get("secret", "")), secret):
                    return self._send(403, b"forbidden", "text/plain")
                p, ws = str(d.get("path") or ""), str(d.get("ws") or "")
                ws = "".join(c for c in ws if c.isalnum() or c in "-_")[:200_000]
                tok = register(p) if p else (secrets.token_hex(8) if ws else None)
                if tok and d.get("deliver"):
                    with ilock:
                        inbox[tok] = {"token": tok if p else None, "ws": ws}
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
        BROWSER[0] = proc
        if proc is not None:
            proc.wait()
            if time.time() - t0 < 5 and not QUIT.is_set():
                # browser gaf het venster door aan een ander proces: val terug op idle-detectie
                log("browser stopte meteen; idle-modus")
                proc = None
        if proc is None:
            while time.time() - last[0] < IDLE_LIMIT and not QUIT.wait(15):
                pass
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
