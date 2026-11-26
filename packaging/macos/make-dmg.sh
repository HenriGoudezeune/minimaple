#!/usr/bin/env bash
# Maakt mini-Maple.app (AppleScript-applet + eigen Python) en een .dmg. Draait op macOS.
# Gebruik: make-dmg.sh STAGE VERSIE UIT.dmg      (STAGE = uitvoer van posix/stage.sh)
set -euo pipefail
umask 022
STAGE="$(cd "$1" && pwd)"; VERSION="$2"; OUTDMG="$3"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
APP="$WORK/dmg/mini-Maple.app"; mkdir -p "$WORK/dmg"

echo "== applet"
osacompile -o "$APP" "$HERE/mini-Maple.applescript"
RES="$APP/Contents/Resources"
cp -a "$STAGE/python" "$STAGE/app" "$RES/"

echo "== icoon"
"$STAGE/python/bin/python3" -I - "$STAGE/app/mini-maple.png" "$WORK/mini-Maple.iconset" <<'PYEOF'
import os, sys
from PIL import Image
src = Image.open(sys.argv[1]).convert("RGBA"); out = sys.argv[2]; os.makedirs(out)
for s in (16, 32, 128, 256, 512):
    src.resize((s, s), Image.LANCZOS).save(f"{out}/icon_{s}x{s}.png")
    src.resize((2 * s, 2 * s), Image.LANCZOS).save(f"{out}/icon_{s}x{s}@2x.png")
PYEOF
iconutil -c icns -o "$RES/applet.icns" "$WORK/mini-Maple.iconset"
rm -f "$RES/Assets.car"

echo "== Info.plist"
"$STAGE/python/bin/python3" -I - "$APP/Contents/Info.plist" "$VERSION" <<'PYEOF'
import plistlib, sys
p, ver = sys.argv[1], sys.argv[2]
with open(p, "rb") as f:
    d = plistlib.load(f)
d.pop("CFBundleIconName", None)
d.update({
    "CFBundleIdentifier": "be.hydrargyrum.minimaple",
    "CFBundleName": "mini-Maple", "CFBundleDisplayName": "mini-Maple",
    "CFBundleShortVersionString": ver, "CFBundleVersion": ver,
    "CFBundleIconFile": "applet",
    "LSMinimumSystemVersion": __import__("os").environ.get("MACOSX_DEPLOYMENT_TARGET", "11.0"),
    "NSHumanReadableCopyright": "MIT-licentie, github.com/HenriGoudezeune/minimaple",
    "CFBundleDocumentTypes": [
        {"CFBundleTypeName": "Maple-werkblad", "CFBundleTypeRole": "Editor", "LSHandlerRank": "Alternate",
         "CFBundleTypeExtensions": ["mw"], "CFBundleTypeIconFile": "applet",
         "LSItemContentTypes": ["be.hydrargyrum.minimaple.mw"]},
        {"CFBundleTypeName": "Maple-broncode", "CFBundleTypeRole": "Editor", "LSHandlerRank": "Alternate",
         "CFBundleTypeExtensions": ["mpl"], "CFBundleTypeIconFile": "applet",
         "LSItemContentTypes": ["be.hydrargyrum.minimaple.mpl"]},
    ],
    "UTImportedTypeDeclarations": [
        {"UTTypeIdentifier": "be.hydrargyrum.minimaple.mw", "UTTypeDescription": "Maple-werkblad",
         "UTTypeConformsTo": ["public.xml", "public.data"],
         "UTTypeTagSpecification": {"public.filename-extension": ["mw"]}},
        {"UTTypeIdentifier": "be.hydrargyrum.minimaple.mpl", "UTTypeDescription": "Maple-broncode",
         "UTTypeConformsTo": ["public.plain-text"],
         "UTTypeTagSpecification": {"public.filename-extension": ["mpl"]}},
    ],
    "CFBundleURLTypes": [{"CFBundleURLName": "be.hydrargyrum.minimaple", "CFBundleURLSchemes": ["minimaple"]}],
})
with open(p, "wb") as f:
    plistlib.dump(d, f)
PYEOF
plutil -lint "$APP/Contents/Info.plist"

echo "== rooktest"
PYTHONDONTWRITEBYTECODE=1 "$RES/python/bin/python3" -s -c 'import sys; sys.path.insert(0, sys.argv[1]); from minimaple.interp import Interpreter; print(Interpreter().run("int(x^2,x);")[0]["text"])' "$RES/app"

echo "== ad-hoc ondertekenen"
find "$RES/python" "$RES/app" -type f \( -perm -u+x -o -name '*.so' -o -name '*.dylib' \) -print0 |
  while IFS= read -r -d '' f; do
    if file -b "$f" | grep -q Mach-O; then codesign -f -s - "$f" 2>/dev/null || echo "   niet ondertekend: $f"; fi
  done
codesign -f -s - "$APP"
codesign --verify --strict "$APP" && echo "   handtekening ok"

echo "== dmg"
ln -s /Applications "$WORK/dmg/Applications"
rm -f "$OUTDMG"
hdiutil create -volname "mini-Maple" -srcfolder "$WORK/dmg" -ov -format UDZO -fs HFS+ "$OUTDMG"
ls -lh "$OUTDMG"
