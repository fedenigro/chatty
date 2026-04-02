#!/usr/bin/env bash
# build_app.sh — builds Chatty.app from the current project directory
# and installs it to /Applications.
#
# Usage (from the project folder):
#   bash build_app.sh [--python /path/to/python3] [--source /path/to/project]
#
# Defaults:
#   --python   first python3 found in PATH that has all deps installed
#   --source   directory containing this script

set -euo pipefail

# ── Parse args ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$SCRIPT_DIR"
PYTHON=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --python) PYTHON="$2"; shift 2 ;;
        --source) SOURCE_DIR="$2"; shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# ── Find Python ───────────────────────────────────────────────────────────────
if [[ -z "$PYTHON" ]]; then
    for candidate in \
        "$(command -v python3.13 2>/dev/null)" \
        "$(command -v python3.12 2>/dev/null)" \
        "$(command -v python3.11 2>/dev/null)" \
        "$(command -v python3 2>/dev/null)" \
        "/opt/homebrew/bin/python3" \
        "$HOME/.pyenv/shims/python3"
    do
        if [[ -x "$candidate" ]] && "$candidate" -c "import rumps, whisper" 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    done
fi

if [[ -z "$PYTHON" ]]; then
    echo "❌  Could not find a Python with Chatty's dependencies installed."
    echo "    Run install.sh first, or pass --python /path/to/python3"
    exit 1
fi

# Resolve pyenv shims → real binary so the .app works without a shell environment
if [[ "$PYTHON" == *"/shims/"* ]]; then
    REAL="$(PYENV_VERSION="" "$PYTHON" -c 'import sys; print(sys.executable)' 2>/dev/null || true)"
    [[ -x "$REAL" ]] && PYTHON="$REAL"
fi
PYTHON="$(realpath "$PYTHON")"
echo "✔  Python: $PYTHON"
echo "✔  Source: $SOURCE_DIR"

# ── Scaffold .app ─────────────────────────────────────────────────────────────
APP_NAME="Chatty"
APP="$SOURCE_DIR/$APP_NAME.app"
BUNDLE_ID="com.chatty.dictation"

echo "→  Building $APP …"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
mkdir -p "$APP/Contents/Resources"

# ── Launcher script ───────────────────────────────────────────────────────────
cat > "$APP/Contents/MacOS/$APP_NAME" <<LAUNCHER
#!/usr/bin/env bash
exec "$PYTHON" "$SOURCE_DIR/app.py"
LAUNCHER
chmod +x "$APP/Contents/MacOS/$APP_NAME"

# ── Icon (.icns from SVG) ─────────────────────────────────────────────────────
SVG="$SOURCE_DIR/assets/mic_on.svg"
ICONSET="$SOURCE_DIR/_build_iconset.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"

"$PYTHON" - "$SVG" "$ICONSET" <<'PYICON'
import sys, os
import cairosvg
svg, out = sys.argv[1], sys.argv[2]
sizes = [
    ("icon_16x16.png",       16),
    ("icon_16x16@2x.png",    32),
    ("icon_32x32.png",       32),
    ("icon_32x32@2x.png",    64),
    ("icon_128x128.png",    128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png",    256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png",    512),
    ("icon_512x512@2x.png",1024),
]
for name, px in sizes:
    cairosvg.svg2png(url=svg, write_to=os.path.join(out, name),
                     output_width=px, output_height=px)
print("  icon renders done")
PYICON

iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/$APP_NAME.icns"
rm -rf "$ICONSET"

# ── Info.plist ────────────────────────────────────────────────────────────────
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>              <string>$APP_NAME</string>
  <key>CFBundleDisplayName</key>       <string>$APP_NAME</string>
  <key>CFBundleIdentifier</key>        <string>$BUNDLE_ID</string>
  <key>CFBundleVersion</key>           <string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleExecutable</key>        <string>$APP_NAME</string>
  <key>CFBundleIconFile</key>          <string>$APP_NAME</string>
  <key>CFBundlePackageType</key>       <string>APPL</string>
  <key>LSUIElement</key>               <true/>
  <key>LSMinimumSystemVersion</key>    <string>12.0</string>
  <key>NSMicrophoneUsageDescription</key>
  <string>Chatty records your voice to transcribe speech into text.</string>
  <key>NSAppleEventsUsageDescription</key>
  <string>Chatty pastes transcribed text into your active app.</string>
</dict>
</plist>
PLIST

# ── Install to /Applications ──────────────────────────────────────────────────
echo "→  Installing to /Applications …"
rm -rf "/Applications/$APP_NAME.app"
cp -r "$APP" "/Applications/$APP_NAME.app"

echo ""
echo "✅  Chatty.app is in /Applications."
echo "    Open it from Spotlight (⌘ Space → Chatty) or Finder."
