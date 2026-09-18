#!/bin/bash
# DevSeva — © 2026 Raviraj Shetty. All rights reserved.
# DevSeva — build a standalone Mac app that does not need Python installed.
# Double-click this file once, with internet on. Nothing in your DevSeva data is changed.
#
# Optional signing and notarisation (needs a paid Apple Developer account):
#   export DEVSEVA_SIGN_ID="Developer ID Application: Your Name (TEAMID)"
#   export DEVSEVA_NOTARY_PROFILE="devseva-notary"   # created once with: xcrun notarytool store-credentials
# Without these, the app gets a basic ("ad-hoc") signature and macOS asks for "Open Anyway" once.

set -uo pipefail
VERSION="0.8"
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
SRC="$HERE/source"
BUNDLE_RESOURCES="$HERE/DevSeva.app/Contents/Resources"
WORK="$HOME/Library/Caches/DevSevaBuild"
OUT="$HERE/DevSeva Standalone"
LOG="$WORK/build.log"

finish() {
  echo
  echo "$1"
  echo
  read -r -p "Press Return to close this window. " _
  exit "${2:-0}"
}
step() { echo; echo "==> $1"; }
fail() { finish "BUILD STOPPED: $1
Nothing was changed in your DevSeva data. Send a screenshot of this window (and $LOG) for help." 1; }

clear
echo "DevSeva $VERSION — standalone app builder"
echo "This takes about 2–5 minutes and downloads the free PyInstaller tool (about 10 MB)."

[ "$(uname)" = "Darwin" ] || fail "this builder runs on macOS only."
[ -f "$SRC/app.py" ] || fail "the source folder is missing. Keep this file next to the source folder and DevSeva.app."
[ -f "$BUNDLE_RESOURCES/developer.key" ] || fail "no developer passphrase is set yet. Open DevSeva.app, press Command+Shift+D (or click the version at the bottom 5 times), create the developer passphrase, quit DevSeva, then run this again. Copies built without it cannot be factory-reset."
mkdir -p "$WORK" || fail "could not create $WORK"
: > "$LOG"

step "Finding Python 3.10+ with Tk (used only to build)"
PY=""
for candidate in \
  /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
  /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if [ -x "$candidate" ] && "$candidate" -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3,10) and tkinter.TkVersion >= 8.6 else 1)' >/dev/null 2>&1; then
    PY="$candidate"; break
  fi
done
[ -n "$PY" ] || fail "no Python 3.10+ with Tk 8.6 was found. Install Python from python.org (it includes Tk), then run this again."
echo "Using $("$PY" --version) at $PY"

step "Preparing a private build environment"
if [ ! -x "$WORK/venv/bin/python" ]; then
  "$PY" -m venv "$WORK/venv" >>"$LOG" 2>&1 || fail "could not create the build environment."
fi
"$WORK/venv/bin/python" -m pip install --disable-pip-version-check -q --upgrade "pip" "pyinstaller>=6.10,<7" >>"$LOG" 2>&1 \
  || fail "could not download PyInstaller. Check the internet connection and try again."

step "Checking the DevSeva source files"
rm -rf "$WORK/src" "$WORK/dist" "$WORK/build"
mkdir -p "$WORK/src"
for f in app.py core.py kannada.py mobile.py security.py importer.py eventday.py widgets.py icons.py qr.py qrcodegen.py developer.py mobile.html NOTICE.txt; do
  cp "$SRC/$f" "$WORK/src/" || fail "missing $f inside DevSeva.app."
done
cp "$BUNDLE_RESOURCES/developer.key" "$WORK/src/" || fail "developer passphrase data is unavailable."
(cd "$WORK/src" && PYTHONDONTWRITEBYTECODE=1 "$WORK/venv/bin/python" app.py --selftest) || fail "the self-test failed before building."

step "Building DevSeva.app (standalone)"
(cd "$WORK/src" && "$WORK/venv/bin/pyinstaller" --noconfirm --clean --windowed \
  --name DevSeva --osx-bundle-identifier local.devseva.standalone \
  --add-data "$WORK/src/mobile.html:." --add-data "$WORK/src/developer.key:." --add-data "$WORK/src/NOTICE.txt:." \
  --distpath "$WORK/dist" --workpath "$WORK/build" --specpath "$WORK" app.py) >>"$LOG" 2>&1 \
  || fail "PyInstaller could not build the app."
APP="$WORK/dist/DevSeva.app"
[ -d "$APP" ] || fail "the built app was not found."
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP/Contents/Info.plist" >>"$LOG" 2>&1
/usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string DevSeva" "$APP/Contents/Info.plist" >>"$LOG" 2>&1
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$APP/Contents/Info.plist" >>"$LOG" 2>&1
/usr/libexec/PlistBuddy -c "Add :NSHumanReadableCopyright string © 2026 Raviraj Shetty. All rights reserved." "$APP/Contents/Info.plist" >>"$LOG" 2>&1

step "Testing the built app"
"$APP/Contents/MacOS/DevSeva" --selftest || fail "the built app failed its self-test."

step "Signing"
if [ -n "${DEVSEVA_SIGN_ID:-}" ]; then
  codesign --force --deep --options runtime --timestamp --sign "$DEVSEVA_SIGN_ID" "$APP" >>"$LOG" 2>&1 \
    || fail "signing with your Developer ID failed."
  if [ -n "${DEVSEVA_NOTARY_PROFILE:-}" ]; then
    step "Notarising with Apple (can take a few minutes)"
    ditto -c -k --keepParent "$APP" "$WORK/notarize.zip"
    xcrun notarytool submit "$WORK/notarize.zip" --keychain-profile "$DEVSEVA_NOTARY_PROFILE" --wait >>"$LOG" 2>&1 \
      || fail "Apple notarisation was not accepted (details in the log)."
    xcrun stapler staple "$APP" >>"$LOG" 2>&1 || fail "could not attach the notarisation ticket."
    SIGNED="signed and notarised"
  else
    SIGNED="signed with your Developer ID (not notarised)"
  fi
else
  codesign --force --deep --sign - "$APP" >>"$LOG" 2>&1 || fail "ad-hoc signing failed."
  SIGNED="ad-hoc signed (macOS will ask for Open Anyway the first time)"
fi
codesign --verify --deep "$APP" >>"$LOG" 2>&1 || fail "the signature did not verify."

step "Saving the result"
mkdir -p "$OUT"
rm -rf "$OUT/DevSeva.app"
ditto "$APP" "$OUT/DevSeva.app" || fail "could not copy the app to $OUT."
ARCH="$(uname -m)"
ZIP="$OUT/DevSeva-$VERSION-standalone-mac-$ARCH.zip"
rm -f "$ZIP"
ditto -c -k --keepParent "$OUT/DevSeva.app" "$ZIP"
open "$OUT"

finish "DONE. The standalone app is in the folder \"DevSeva Standalone\" next to this file:
  • DevSeva.app — drag it into Applications (replace the older DevSeva).
  • $(basename "$ZIP") — the copy to give to other temples (it carries your developer passphrase lock).
Signature: $SIGNED.
Built for this Mac's processor ($ARCH). Other Macs with the same kind of processor can run it without Python.
It uses the same DevSeva data folder as before."
