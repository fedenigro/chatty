#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║               Chatty — one-command installer                 ║
# ║                                                              ║
# ║  curl -fsSL https://your-link/install.sh | bash             ║
# ║   — or —                                                     ║
# ║  bash install.sh                                             ║
# ╚══════════════════════════════════════════════════════════════╝
#
# What this does:
#   1. Installs Homebrew (if missing)
#   2. Installs Python 3.12 + ffmpeg via Homebrew
#   3. Copies app files to ~/.chatty/
#   4. Installs all Python dependencies
#   5. Builds Chatty.app and puts it in /Applications
#
# Requirements: macOS 12+, internet connection (first run only)

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${BLUE}→${NC}  $*"; }
success() { echo -e "${GREEN}✔${NC}  $*"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $*"; }
die()     { echo -e "${RED}✘${NC}  $*" >&2; exit 1; }
header()  { echo -e "\n${BOLD}$*${NC}"; }

# ── macOS guard ───────────────────────────────────────────────────────────────
[[ "$(uname)" == "Darwin" ]] || die "Chatty requires macOS."

header "🎙  Chatty Installer"
echo ""

# ── Locate project source ─────────────────────────────────────────────────────
# If run via "curl | bash" there is no __file__; fall back to cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$PWD}")" 2>/dev/null && pwd || echo "$PWD")"
# Verify it looks like the Chatty source folder
if [[ ! -f "$SCRIPT_DIR/app.py" ]]; then
    die "install.sh must be run from the Chatty project folder (the one containing app.py)."
fi

INSTALL_DIR="$HOME/.chatty"
APP_NAME="Chatty"

# ── 1. Homebrew ───────────────────────────────────────────────────────────────
header "Step 1 — Homebrew"
if command -v brew &>/dev/null; then
    success "Homebrew already installed ($(brew --version | head -1))"
else
    info "Installing Homebrew …"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add brew to PATH for this session (Apple Silicon vs Intel)
    if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    else
        eval "$(/usr/local/bin/brew shellenv)"
    fi
    success "Homebrew installed."
fi

# ── 2. ffmpeg ─────────────────────────────────────────────────────────────────
header "Step 2 — ffmpeg"
if command -v ffmpeg &>/dev/null; then
    success "ffmpeg already installed."
else
    info "Installing ffmpeg …"
    brew install ffmpeg
    success "ffmpeg installed."
fi

# ── 3. Python 3.12 ───────────────────────────────────────────────────────────
header "Step 3 — Python 3.12"
PYTHON=""
# Prefer homebrew python for a clean, relocatable install
for candidate in \
    "$(brew --prefix)/bin/python3.13" \
    "$(brew --prefix)/bin/python3.12" \
    "$(brew --prefix)/bin/python3.11" \
    "$(brew --prefix)/bin/python3" \
    "$(command -v python3.13 2>/dev/null)" \
    "$(command -v python3.12 2>/dev/null)" \
    "$(command -v python3 2>/dev/null)"
do
    if [[ -x "$candidate" ]]; then
        VER="$("$candidate" -c 'import sys; print(sys.version_info[:2])')"
        if python3 -c "assert $VER >= (3,10)" 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    info "Installing Python 3.12 via Homebrew …"
    brew install python@3.12
    PYTHON="$(brew --prefix)/bin/python3.12"
fi

PYTHON="$(realpath "$PYTHON")"
success "Python: $PYTHON ($("$PYTHON" --version))"

# ── 4. Copy app files ─────────────────────────────────────────────────────────
header "Step 4 — Copy app files → $INSTALL_DIR"
mkdir -p "$INSTALL_DIR/assets"

FILES=(app.py recorder.py transcriber.py paste.py overlay.py config.py)
for f in "${FILES[@]}"; do
    cp "$SCRIPT_DIR/$f" "$INSTALL_DIR/$f"
done
cp -r "$SCRIPT_DIR/assets/"* "$INSTALL_DIR/assets/"
success "App files copied."

# ── 5. Python dependencies ────────────────────────────────────────────────────
header "Step 5 — Python dependencies"
info "This may take a few minutes on the first run (torch + whisper are large) …"
"$PYTHON" -m pip install --upgrade pip --quiet
"$PYTHON" -m pip install \
    rumps \
    pynput \
    sounddevice \
    numpy \
    openai-whisper \
    pyobjc-core \
    pyobjc-framework-Cocoa \
    pyobjc-framework-Quartz \
    pyperclip \
    cairosvg \
    --quiet
success "Dependencies installed."

# ── 6. Build & install Chatty.app ────────────────────────────────────────────
header "Step 6 — Build Chatty.app"
bash "$SCRIPT_DIR/build_app.sh" --python "$PYTHON" --source "$INSTALL_DIR"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✅  Chatty is installed!${NC}"
echo ""
echo "  Launch:      ⌘ Space → type 'Chatty' → Enter"
echo "  Use:         Press Cmd+Shift+Space to start/stop dictation"
echo ""
echo -e "${YELLOW}First launch:${NC} macOS will ask for Accessibility + Microphone permissions."
echo "  Go to System Settings → Privacy & Security and enable both for Chatty."
echo ""
