#!/usr/bin/env bash
# Maakt mini-Maple-x86_64.AppImage en mini-maple_<versie>_amd64.deb uit een staging-map van posix/stage.sh.
# Gebruik: make-packages.sh STAGE VERSIE DIST   (APPIMAGETOOL=pad, anders wordt hij gedownload)
set -euo pipefail
umask 022
STAGE="$(cd "$1" && pwd)"; VERSION="$2"; mkdir -p "$3"; DIST="$(cd "$3" && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

echo "== AppImage"
AD="$WORK/AppDir"; mkdir -p "$AD/usr/lib/mini-maple"
cp -a "$STAGE/python" "$STAGE/app" "$AD/usr/lib/mini-maple/"
cat > "$AD/AppRun" <<'SH'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/mini-maple/python/bin/python3" -s "$HERE/usr/lib/mini-maple/app/launcher.py" "$@"
SH
chmod 755 "$AD/AppRun"
cp "$HERE/mini-maple.desktop" "$AD/mini-maple.desktop"
cp "$STAGE/app/mini-maple.png" "$AD/mini-maple.png"; ln -s mini-maple.png "$AD/.DirIcon"
mkdir -p "$AD/usr/share/metainfo"
TOOL="${APPIMAGETOOL:-}"
if [ -z "$TOOL" ]; then
  TOOL="$WORK/appimagetool"
  curl -fsSL --retry 3 -o "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi
chmod -R u+rwX,go+rX,go-w "$AD"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$AD" "$DIST/mini-Maple-x86_64.AppImage"
chmod 755 "$DIST/mini-Maple-x86_64.AppImage"

echo "== .deb"
R="$WORK/deb"; mkdir -p "$R/DEBIAN" "$R/opt/mini-maple" "$R/usr/bin" "$R/usr/share/applications" \
  "$R/usr/share/mime/packages" "$R/usr/share/icons/hicolor/256x256/apps"
cp -a "$STAGE/python" "$STAGE/app" "$R/opt/mini-maple/"
cat > "$R/usr/bin/mini-maple" <<'SH'
#!/bin/sh
exec /opt/mini-maple/python/bin/python3 -s /opt/mini-maple/app/launcher.py "$@"
SH
chmod 755 "$R/usr/bin/mini-maple"
cp "$HERE/mini-maple.desktop" "$R/usr/share/applications/"
cp "$HERE/mini-maple.xml" "$R/usr/share/mime/packages/"
cp "$STAGE/app/mini-maple.png" "$R/usr/share/icons/hicolor/256x256/apps/"
SIZE=$(du -sk --exclude=DEBIAN "$R" | cut -f1)
cat > "$R/DEBIAN/control" <<CTL
Package: mini-maple
Version: $VERSION
Section: math
Priority: optional
Architecture: amd64
Depends: libc6 (>= 2.28)
Recommends: xdg-utils
Installed-Size: $SIZE
Maintainer: Henri Goudezeune <67186380+HenriGoudezeune@users.noreply.github.com>
Homepage: https://github.com/HenriGoudezeune/minimaple
Description: Offline rekenwerkblad met Maple-syntax
 mini-Maple draait een lokale rekenkern (sympy, numpy, scipy, matplotlib) met een
 eigen Python en opent de worksheet in een app-venster van je browser.
 Opent .mw- en .mpl-bestanden en minimaple://-links.
CTL
for s in postinst postrm; do
  cat > "$R/DEBIAN/$s" <<'SH'
#!/bin/sh
set -e
command -v update-mime-database >/dev/null 2>&1 && update-mime-database /usr/share/mime || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
exit 0
SH
  chmod 755 "$R/DEBIAN/$s"
done
chmod -R u+rwX,go+rX,go-w "$R"
DEB="$DIST/mini-maple_${VERSION}_amd64.deb"
dpkg-deb --root-owner-group -Zxz --build "$R" "$DEB"
cp "$DEB" "$DIST/mini-maple_amd64.deb"
ls -lh "$DIST"
