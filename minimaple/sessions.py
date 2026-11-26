"""Sessiebeheer met worker-processen: elke sessie draait in een eigen proces, zodat een
vastgelopen berekening na een timeout gedood kan worden zonder de server te blokkeren.
Gedeeld door mcp_server.py en web/server.py. Geen shell/bestandstoegang vanuit Maple-code."""
import multiprocessing as mp
import os
import tempfile
import threading
import time

DEFAULT_TIMEOUT = float(os.environ.get("MINIMAPLE_TIMEOUT", "60"))


_STUB_ENV = {}


def _stub_run(code):
    """Stub tot interp.py bestaat: zelfde dict-structuur als het contract."""
    if "while true" in code:
        time.sleep(1000)
    out = []
    for s in [p.strip() for p in code.replace("\n", " ").split(";") if p.strip()]:
        show = not s.endswith(":")
        s = s.rstrip(":").strip()
        if ":=" in s:
            k, v = [x.strip() for x in s.split(":=", 1)]
            _STUB_ENV[k] = v
            txt = f"{k} := {v}"
        else:
            txt = _STUB_ENV.get(s, s)
        out.append({"stmt": s, "show": show, "text": txt, "latex": txt, "plots": [], "error": None})
    return out


def _worker(conn):
    lim = int(os.environ.get("MINIMAPLE_MEM_MB", "0"))
    if lim:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (lim << 20, lim << 20))
    os.environ.setdefault("MPLBACKEND", "Agg")
    try:
        from .interp import Interpreter
        it = Interpreter()
        run = it.run
    except ImportError:
        run = _stub_run
    while True:
        try:
            code = conn.recv()
        except EOFError:
            return
        if code is None:
            return
        try:
            res = run(code)
            clean = []
            for r in res:
                pngs = []
                for p in r.get("plots") or []:
                    fd, path = tempfile.mkstemp(suffix=".png")
                    os.close(fd)
                    try:
                        p.render(path)
                        with open(path, "rb") as f:
                            pngs.append(f.read())
                    except Exception as e:  # plotfout mag de rest niet breken
                        r["error"] = (r.get("error") or "") + f" [plot: {e}]"
                    finally:
                        try: os.unlink(path)
                        except OSError: pass
                clean.append({"stmt": r.get("stmt", ""), "show": r.get("show", True),
                              "text": r.get("text", ""), "latex": r.get("latex"),
                              "plots": pngs, "error": r.get("error")})
            conn.send(("ok", clean))
        except BaseException as e:
            conn.send(("err", f"{type(e).__name__}: {e}"))


class _Session:
    def __init__(self):
        self.ctx = mp.get_context("spawn")
        self.lock = threading.Lock()
        self.proc = None
        self.conn = None
        self.last = time.time()

    def _start(self):
        parent, child = self.ctx.Pipe()
        self.proc = self.ctx.Process(target=_worker, args=(child,), daemon=True)
        self.proc.start()
        child.close()
        self.conn = parent

    def kill(self):
        if self.proc is not None:
            try:
                self.proc.kill()
                self.proc.join(2)
            except Exception:
                pass
        self.proc = self.conn = None

    def run(self, code, timeout):
        with self.lock:
            self.last = time.time()
            if self.proc is None or not self.proc.is_alive():
                self.kill()
                self._start()
            self.conn.send(code)
            if not self.conn.poll(timeout):
                self.kill()
                return [{"stmt": code, "show": True, "text": "", "latex": None, "plots": [],
                         "error": f"Time limit exceeded ({timeout:g} s); session reset, earlier definitions lost."}]
            try:
                kind, val = self.conn.recv()
            except (EOFError, OSError):
                self.kill()
                return [{"stmt": code, "show": True, "text": "", "latex": None, "plots": [],
                         "error": "Worker process crashed; session reset."}]
            if kind == "err":
                return [{"stmt": code, "show": True, "text": "", "latex": None, "plots": [], "error": val}]
            return val


class SessionManager:
    def __init__(self, max_sessions=int(os.environ.get("MINIMAPLE_MAX_SESSIONS", "32"))):
        self.sessions = {}
        self.lock = threading.Lock()
        self.max = max_sessions
        self.slots = threading.BoundedSemaphore(int(os.environ.get("MINIMAPLE_MAX_PARALLEL", "64")))

    def _get(self, name):
        with self.lock:
            s = self.sessions.get(name)
            if s is None:
                if len(self.sessions) >= self.max:  # oudste sessie opruimen
                    old = min(self.sessions, key=lambda k: self.sessions[k].last)
                    self.sessions.pop(old).kill()
                s = self.sessions[name] = _Session()
            return s

    def eval(self, code, session="default", timeout=None):
        if not self.slots.acquire(timeout=5):
            return [{"stmt": code, "show": True, "text": "", "latex": None, "plots": [], "error": "Server busy, try again shortly."}]
        try:
            return self._get(session).run(code, timeout or DEFAULT_TIMEOUT)
        finally:
            self.slots.release()

    def reset(self, session="default"):
        with self.lock:
            s = self.sessions.pop(session, None)
        if s:
            s.kill()

    def close(self):
        for n in list(self.sessions):
            self.reset(n)


def commands():
    """-> (builtins, {pakket: namen}) uit values.BUILTINS/PACKAGES (laadt de modules)."""
    from . import values
    import importlib
    for m in ("core_fns", "calc", "linalg", "vecalc", "plots", "imagetools", "interp"):
        try:
            importlib.import_module(f"minimaple.{m}")
        except ImportError:
            pass
    return sorted(values.BUILTINS), {k: sorted(set(v)) for k, v in values.PACKAGES.items()}


def help_for(name):
    from . import values
    commands()
    fn = values.BUILTINS.get(name)
    if fn is None:
        return None
    pk = [p for p, ns in values.PACKAGES.items() if name in ns]
    doc = (fn.__doc__ or "").strip() or "(no documentation)"
    return f"{name}" + (f"  [package: {', '.join(pk)}]" if pk else "") + f"\n{doc}"
