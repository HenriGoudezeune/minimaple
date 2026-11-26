"""Command-line: REPL, `python -m minimaple file.mpl` en `python -m minimaple -e "code"`."""
import os
import sys
import time

OUT_DIR = os.path.expanduser("~/work/minimaple/out")
_counter = [0]


def save_plots(plots):
    paths = []
    os.makedirs(OUT_DIR, exist_ok=True)
    for p in plots:
        _counter[0] += 1
        path = os.path.join(OUT_DIR, f"plot_{time.strftime('%Y%m%d_%H%M%S')}_{_counter[0]}.png")
        p.render(path)
        paths.append(path)
    return paths


def show_results(results, out=sys.stdout):
    for r in results:
        if r.get("error"):
            print(r["error"], file=out)
            continue
        if r.get("show", True) and r.get("text"):
            print(r["text"], file=out)
        for path in (save_plots(r["plots"]) if r.get("show", True) and r.get("plots") else []):
            print(f"[plot] {path}", file=out)


def _complete(src):
    """Is de invoer afgerond (eindigt op ; of : buiten strings/commentaar en blokken gesloten)?"""
    s = src.rstrip()
    if not s:
        return False
    try:
        from .parser import tokenize
        toks = tokenize(s)
    except Exception:
        return True
    toks = [t for t in toks if t.t != "eof"]
    if not toks:
        return True
    last = toks[-1]
    if not (last.t == "op" and last.v in (";", ":")):
        return False
    depth = 0
    opens = {"proc", "if", "do", "try", "for", "while"}
    for t in toks:
        if t.t == "name":
            if t.v in ("proc", "if", "do", "try"):
                depth += 1
            elif t.v in ("od", "fi"):
                depth -= 1
            elif t.v == "end":
                depth -= 1
        elif t.t == "op" and t.v in "([{":
            depth += 1
        elif t.t == "op" and t.v in ")]}":
            depth -= 1
    # `end proc`/`end if`/`end do` tellen als een enkele sluiter: 'proc','if','do' na 'end' compenseren
    for a, b in zip(toks, toks[1:]):
        if a.t == "name" and a.v == "end" and b.t == "name" and b.v in ("proc", "if", "do", "try"):
            depth += 1
    return depth <= 0


def repl(it):
    try:
        import readline  # noqa
    except ImportError:
        pass
    print("mini-Maple. Eindig een commando met ; of :. Stoppen: quit")
    buf = ""
    while True:
        try:
            line = input("> " if not buf else "  ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not buf and line.strip() in ("quit", "exit", "done", "quit;", "exit;", "done;", "stop"):
            break
        buf += line + "\n"
        if _complete(buf) or buf.strip() == "":
            show_results(it.run(buf))
            buf = ""


def main(argv=None):
    os.environ.setdefault("MPLBACKEND", "Agg")
    argv = list(sys.argv[1:] if argv is None else argv)
    from .interp import Interpreter
    it = Interpreter()
    if argv and argv[0] == "-e":
        code = " ".join(argv[1:])
        res = it.run(code)
        show_results(res)
        return 1 if any(r.get("error") for r in res) else 0
    if argv:
        status = 0
        for path in argv:
            with open(path, encoding="utf-8") as f:
                res = it.run(f.read())
            show_results(res)
            if any(r.get("error") for r in res):
                status = 1
        return status
    if not sys.stdin.isatty():
        res = it.run(sys.stdin.read())
        show_results(res)
        return 1 if any(r.get("error") for r in res) else 0
    repl(it)
    return 0


if __name__ == "__main__":
    sys.exit(main())
