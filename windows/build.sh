#!/usr/bin/env bash
# Bouwt dist/mini-Maple-windows.zip: offline Windows-app (embeddable Python + wheels + minimaple).
# Gebruik:  ./build.sh [pad-naar-minimaple-ui]      (standaard: de repo zelf)
# Herdraaibaar: downloads worden gecachet in cache/; build/ en de zip worden telkens vers gemaakt.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
PYVER="${PYVER:-3.14.10}"                       # Windows embeddable Python (python.org)
PYMM="$(echo "$PYVER" | cut -d. -f1,2)"          # 3.14
PYTAG="$(echo "$PYMM" | tr -d .)"                # 314
HOSTPY="${HOSTPY:-python3}"                      # Linux-python, zelfde minor => .pyc vooraf compileren
VERIFYPY="${VERIFYPY:-python3}"   # venv met sympy e.a. voor de importtest

CACHE="$HERE/cache"; BUILD="$HERE/build"; DIST="$HERE/dist"
STAGE="$BUILD/mini-Maple"; RT="$STAGE/runtime"; SP="$RT/Lib/site-packages"
ZIP="$DIST/mini-Maple-windows.zip"

[ -d "$SRC/minimaple" ] || { echo "geen minimaple-pakket in $SRC" >&2; exit 1; }
mkdir -p "$CACHE/wheels" "$DIST"

echo "== 1. Python $PYVER embeddable"
EMB="$CACHE/python-$PYVER-embed-amd64.zip"
if [ ! -s "$EMB" ]; then
  curl -fsSL --retry 3 -o "$EMB.part" "https://www.python.org/ftp/python/$PYVER/python-$PYVER-embed-amd64.zip"
  mv "$EMB.part" "$EMB"
fi

echo "== 2. wheels (win_amd64, cp$PYTAG)"
PIPPLAT=(--platform win_amd64 --python-version "$PYMM" --implementation cp --abi "cp$PYTAG" --only-binary=:all:)
"$HOSTPY" -m pip download -q --disable-pip-version-check "${PIPPLAT[@]}" \
  -r "$HERE/requirements-win.txt" -d "$CACHE/wheels"
bad=$(ls "$CACHE/wheels" | grep -vE -- '-(win_amd64|none-any)\.whl$' || true)
[ -z "$bad" ] || { echo "FOUT: niet-Windows-wheels: $bad" >&2; exit 1; }

echo "== 3. staging"
rm -rf "$BUILD"; mkdir -p "$RT" "$STAGE/app"
"$HOSTPY" -I -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])' "$EMB" "$RT"
"$HOSTPY" -m pip install -q --disable-pip-version-check --no-compile --no-warn-conflicts --no-index \
  --find-links "$CACHE/wheels" "${PIPPLAT[@]}" --target "$SP" -r "$HERE/requirements-win.txt"
rm -rf "$SP/bin" "$SP/share" "$SP"/*.whl
# _pth: embeddable Python negeert PYTHONPATH; hier staan de zoekpaden.
PTH=$(ls "$RT"/python*._pth)
printf 'python%s.zip\r\n.\r\nLib\\site-packages\r\n..\\app\r\nimport site\r\n' "$PYTAG" > "$PTH"

echo "== 4. minimaple uit $SRC"
# eerst een momentopname (de UI kan intussen wijzigen), daarna precies die kopie in de app
SNAP="$CACHE/src-snapshot"; rm -rf "$SNAP"
"$HOSTPY" -I - "$SRC/minimaple" "$SNAP/minimaple" "$STAGE/app/minimaple" <<'EOF'
import shutil, sys
ign = shutil.ignore_patterns("__pycache__", "*.pyc", "*.png", ".*")
shutil.copytree(sys.argv[1], sys.argv[2], ignore=ign)
shutil.copytree(sys.argv[2], sys.argv[3], ignore=ign)
EOF
cp "$HERE/template/app/launcher.py" "$HERE/template/app/mini-Maple.ico" "$STAGE/app/"
for f in mini-Maple.vbs mini-Maple.bat snelkoppeling-maken.vbs bestandskoppeling-aan.vbs bestandskoppeling-uit.vbs LEESMIJ.txt; do
  sed 's/\r$//; s/$/\r/' "$HERE/template/$f" > "$STAGE/$f"     # CRLF voor Windows
done

echo "== 5. afslanken"
find "$SP" -depth -type d \( -name tests -o -name __pycache__ \) -exec rm -rf {} +
rm -rf "$SP"/matplotlib/mpl-data/sample_data

echo "== 6. .pyc vooraf compileren (snellere eerste start)"
if [ "$("$HOSTPY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')" = "$PYMM" ]; then
  "$HOSTPY" -I -W ignore -m compileall -q -j0 --invalidation-mode unchecked-hash -s "$STAGE/" -p "" \
    "$SP" "$STAGE/app/minimaple" >/dev/null || echo "   (enkele bestanden niet gecompileerd, niet erg)"
else
  echo "   overgeslagen: $HOSTPY is geen Python $PYMM"
fi

echo "== 7. geheimencontrole"
leak=$(find "$STAGE" \( -name '*.p12' -o -name '*.pem' -o -name '*.key' -o -name 'state.json' -o -name '.env' \
        -o -name 'browser-profile' -o -name '.git' -o -name '.venv' \) -print)
leak2=$(grep -rlIE 'BEGIN [A-Z ]*PRIVATE KEY|gh[p]_[A-Za-z0-9]{20}|sk-[a]nt-|xo[x][bp]-' "$STAGE/app" "$STAGE"/*.vbs "$STAGE"/*.bat "$STAGE"/*.txt || true)
[ -z "$leak$leak2" ] || { echo "FOUT: mogelijk geheim: $leak $leak2" >&2; exit 1; }

echo "== 8. zip"
rm -f "$ZIP"
"$HOSTPY" -I - "$BUILD" "$ZIP" <<'EOF'
import os, sys, zipfile
root, out = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for d, dirs, files in os.walk(root):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(d, f)
            z.write(p, os.path.relpath(p, root))
EOF

echo "== 9. controle"
"$HOSTPY" -I "$HERE/tools/verify.py" "$ZIP" "$SNAP" "$VERIFYPY"
if ! diff -rq -x __pycache__ -x '*.pyc' -x '*.png' -x '.*' "$SRC/minimaple" "$SNAP/minimaple" >/dev/null; then
  echo "LET OP: $SRC is tijdens de build gewijzigd; draai build.sh opnieuw voor de nieuwste versie."
fi
ls -lh "$ZIP"
