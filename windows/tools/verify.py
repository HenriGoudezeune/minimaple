"""Controleert dist/mini-Maple-windows.zip zonder Windows.
Gebruik: python3 verify.py ZIP SRC VERIFYPY"""
import hashlib, os, re, subprocess, sys, tempfile, zipfile
from pathlib import Path

zp, src, vpy = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
z = zipfile.ZipFile(zp)
names = set(z.namelist())
R = "mini-Maple/"
fails = []

def need(n):
    if R + n not in names:
        fails.append("ontbreekt: " + n)

for n in ["mini-Maple.vbs", "mini-Maple.bat", "LEESMIJ.txt", "snelkoppeling-maken.vbs",
          "bestandskoppeling-aan.vbs", "bestandskoppeling-uit.vbs", "runtime/python.exe",
          "runtime/pythonw.exe", "app/launcher.py", "app/mini-Maple.ico",
          "app/minimaple/__init__.py", "app/minimaple/web/server.py", "app/minimaple/web/static/index.html"]:
    need(n)
pth = [n for n in names if re.fullmatch(R + r"runtime/python\d+\._pth", n)]
if len(pth) != 1:
    fails.append("geen/meerdere ._pth")
else:
    t = z.read(pth[0]).decode()
    for line in ["Lib\\site-packages", "..\\app", "import site"]:
        if line not in t.splitlines():
            fails.append(f"_pth mist {line!r}")
for pkg in ["sympy", "mpmath", "numpy", "scipy", "matplotlib", "PIL"]:
    need(f"runtime/Lib/site-packages/{pkg}/__init__.py")

# Wheel-tags uit elke .dist-info/WHEEL
tags = set()
for n in names:
    if n.endswith(".dist-info/WHEEL"):
        for line in z.read(n).decode().splitlines():
            if line.startswith("Tag:"):
                tags.add(line.split(":", 1)[1].strip())
badtags = [t for t in tags if not (t.endswith("-none-any") or t.endswith("-win_amd64"))]
if badtags:
    fails.append(f"verkeerde wheel-tags: {badtags}")
linux_bin = [n for n in names if n.endswith(".so") or ".so." in n.rsplit("/", 1)[-1]]
if linux_bin:
    fails.append(f"Linux-binaries: {linux_bin[:5]}")
pyd = [n for n in names if n.endswith(".pyd")]

# Bronnen identiek aan SRC
skip = lambda p: "__pycache__" in p.parts or p.suffix in (".pyc", ".png") or any(x.startswith(".") for x in p.parts)
srcfiles = {p.relative_to(src).as_posix() for p in (src / "minimaple").rglob("*") if p.is_file() and not skip(p.relative_to(src))}
zipfiles = {n[len(R + "app/"):] for n in names if n.startswith(R + "app/minimaple/") and "__pycache__" not in n and not n.endswith("/")}
if srcfiles != zipfiles:
    fails.append(f"bestandsverschil: alleen bron {sorted(srcfiles - zipfiles)[:5]}, alleen zip {sorted(zipfiles - srcfiles)[:5]}")
diff = [f for f in srcfiles & zipfiles if hashlib.sha256((src / f).read_bytes()).digest() != hashlib.sha256(z.read(R + "app/" + f)).digest()]
if diff:
    fails.append(f"inhoud verschilt: {diff[:5]}")

# Importtest onder Linux met de sources uit de zip
with tempfile.TemporaryDirectory() as d:
    for n in names:
        if n.startswith(R + "app/") and "__pycache__" not in n:
            z.extract(n, d)
    app = os.path.join(d, "mini-Maple", "app")
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "import minimaple, minimaple.web.server as S;"
        "assert minimaple.__file__.startswith(sys.argv[1]), minimaple.__file__;"
        "from minimaple.interp import Interpreter;"
        "r = Interpreter().run('int(x^2, x); diff(sin(x), x);');"
        "print(' | '.join(x['text'] for x in r));"
        "import importlib.util as u; s = u.spec_from_file_location('launcher', sys.argv[1] + '/launcher.py');"
        "m = u.module_from_spec(s); s.loader.exec_module(m); print('launcher ok')"
    )
    p = subprocess.run([vpy, "-I", "-c", code, app], capture_output=True, text=True, timeout=300)
    print("importtest:", p.stdout.strip().replace("\n", " / "))
    if p.returncode:
        fails.append("importtest faalt: " + p.stderr[-800:])

size = os.path.getsize(zp) / 1e6
print(f"bestanden: {len(names)}, .pyd: {len(pyd)}, wheel-tags: {sorted(tags)}")
print(f"zip: {size:.1f} MB, uitgepakt: {sum(i.file_size for i in z.infolist()) / 1e6:.0f} MB")
if fails:
    print("FOUT:\n  " + "\n  ".join(fails))
    sys.exit(1)
print("OK: alle controles geslaagd")
