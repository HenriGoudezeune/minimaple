#!/usr/bin/env bash
# Bouwt een zelfstandige mini-Maple-boom voor macOS of Linux:
#   OUT/python  (relocatable CPython van python-build-standalone, via uv)
#   OUT/app     (launcher.py + minimaple + icoon/.desktop/mime)
# Gebruik: stage.sh OUT   (env: PYMM=3.14, UV_PLATFORM=aarch64-apple-darwin|x86_64-apple-darwin|x86_64-manylinux_2_28)
# Vereist: uv, en draait op hetzelfde OS/dezelfde architectuur als het doel (voor compileall en de rooktest).
set -euo pipefail
OUT="$1"; ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYMM="${PYMM:-3.14}"; UV_PLATFORM="${UV_PLATFORM:?}"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
[ ! -e "$OUT/python" ] || { echo "$OUT/python bestaat al" >&2; exit 1; }

echo "== python $PYMM (python-build-standalone)"
export UV_PYTHON_INSTALL_DIR="$OUT/.uvpy"
uv python install --no-bin "$PYMM"
SRCPY="$(uv python find --managed-python --no-project "$PYMM")"
PYHOME="$(cd -P "$(dirname "$(readlink -f "$SRCPY")")/.." && pwd -P)"
cp -a "$PYHOME" "$OUT/python"
rm -rf "$OUT/.uvpy"
PY="$OUT/python/bin/python3"
rm -f "$OUT/python/lib/python$PYMM/EXTERNALLY-MANAGED"
"$PY" -c 'import sys; print(sys.version, sys.prefix)'

echo "== wheels ($UV_PLATFORM)"
uv pip install --python "$PY" --python-platform "$UV_PLATFORM" --only-binary :all: --no-compile \
  --break-system-packages -r "$ROOT/windows/requirements-win.txt"

echo "== app"
mkdir -p "$OUT/app"
cp "$ROOT/windows/template/app/launcher.py" "$OUT/app/"
"$PY" -I - "$ROOT/minimaple" "$OUT/app/minimaple" <<'PYEOF'
import shutil, sys
shutil.copytree(sys.argv[1], sys.argv[2], ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.png", ".*"))
PYEOF
cp "$ROOT/packaging/linux/mini-maple.desktop" "$ROOT/packaging/linux/mini-maple.xml" "$OUT/app/"
"$PY" -I - "$ROOT/windows/assets/mini-Maple.ico" "$OUT/app/mini-maple.png" <<'PYEOF'
import sys
from PIL import Image
ico = Image.open(sys.argv[1]).ico
ico.getimage(max(ico.sizes())).convert("RGBA").save(sys.argv[2])
PYEOF

echo "== afslanken"
L="$OUT/python/lib/python$PYMM"
rm -rf "$L"/{test,idlelib,tkinter,turtledemo,ensurepip,lib2to3} "$L"/lib-dynload/_tkinter* \
       "$OUT"/python/lib/{tcl,tk,itcl,thread}* "$OUT"/python/lib/libtcl* "$OUT"/python/lib/libtk* \
       "$OUT/python/share" "$OUT/python/include"
find "$OUT/python" -depth -type d \( -name tests -o -name __pycache__ \) -exec rm -rf {} +
rm -rf "$L"/site-packages/matplotlib/mpl-data/sample_data

echo "== .pyc vooraf compileren"
"$PY" -I -W ignore -m compileall -q -j0 --invalidation-mode unchecked-hash "$OUT/python/lib" "$OUT/app" >/dev/null \
  || echo "   (enkele bestanden niet gecompileerd, niet erg)"

echo "== rooktest"
(cd / && "$PY" -I -c '
import sys; sys.path.insert(0, sys.argv[1])
import minimaple, minimaple.web.server
from minimaple.interp import Interpreter
print(" | ".join(r["text"] for r in Interpreter().run("int(x^2, x); diff(sin(x), x); plot(sin(x), x=0..1);")))
import importlib.util as u; s = u.spec_from_file_location("launcher", sys.argv[1] + "/launcher.py")
m = u.module_from_spec(s); s.loader.exec_module(m); print("launcher ok")
' "$OUT/app")

echo "== geheimencontrole"
leak=$(find "$OUT" \( -name '*.p12' -o -name '*.pem' -o -name '*.key' -o -name 'state.json' -o -name '.env' -o -name '.git' \) -print | grep -v '/certifi/' || true)
[ -z "$leak" ] || { echo "FOUT: mogelijk geheim: $leak" >&2; exit 1; }
du -sh "$OUT"
