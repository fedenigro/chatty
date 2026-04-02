#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
# ║               Chatty — one-command installer                 ║
# ║                                                              ║
# ║  curl -fsSL https://raw.githubusercontent.com/fedenigro/   ║
# ║             chatty/main/install.sh | bash                   ║
# ╚══════════════════════════════════════════════════════════════╝
set -euo pipefail

REPO="fedenigro/chatty"
BRANCH="main"
INSTALL_DIR="$HOME/.chatty"
APP_NAME="Chatty"

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'
BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${BLUE}→${NC}  $*"; }
success() { echo -e "${GREEN}✔${NC}  $*"; }
die()     { echo -e "\033[0;31m✘${NC}  $*" >&2; exit 1; }
header()  { echo -e "\n${BOLD}$*${NC}"; }

[[ "$(uname)" == "Darwin" ]] || die "Chatty requires macOS."

header "🎙  Chatty Installer"
echo ""

# ── 1. Homebrew ───────────────────────────────────────────────────────────────
header "Step 1 — Homebrew"
if ! command -v brew &>/dev/null; then
    info "Installing Homebrew …"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    [[ -f /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)" \
                                    || eval "$(/usr/local/bin/brew shellenv)"
fi
success "Homebrew ready."

# ── 2. ffmpeg ─────────────────────────────────────────────────────────────────
header "Step 2 — ffmpeg"
if ! command -v ffmpeg &>/dev/null; then
    info "Installing ffmpeg …"
    brew install ffmpeg
fi
success "ffmpeg ready."

# ── 3. Python ─────────────────────────────────────────────────────────────────
header "Step 3 — Python 3.12"
PYTHON=""
for candidate in \
    "$(brew --prefix 2>/dev/null)/bin/python3.13" \
    "$(brew --prefix 2>/dev/null)/bin/python3.12" \
    "$(brew --prefix 2>/dev/null)/bin/python3.11" \
    "$(brew --prefix 2>/dev/null)/bin/python3" \
    "$(command -v python3.13 2>/dev/null || true)" \
    "$(command -v python3.12 2>/dev/null || true)" \
    "$(command -v python3    2>/dev/null || true)"
do
    if [[ -x "$candidate" ]] && "$candidate" -c \
        "import sys; assert sys.version_info>=(3,10)" 2>/dev/null; then
        PYTHON="$candidate"; break
    fi
done

if [[ -z "$PYTHON" ]]; then
    info "Installing Python 3.12 via Homebrew …"
    brew install python@3.12
    PYTHON="$(brew --prefix)/bin/python3.12"
fi
PYTHON="$(realpath "$PYTHON")"
success "Python: $PYTHON ($("$PYTHON" --version))"

# ── 4. Download app files from GitHub ────────────────────────────────────────
header "Step 4 — Download Chatty files"
mkdir -p "$INSTALL_DIR/assets"

BASE="https://raw.githubusercontent.com/$REPO/$BRANCH"

FILES=(
    app.py recorder.py transcriber.py
    paste.py overlay.py config.py
    build_app.sh
)
for f in "${FILES[@]}"; do
    info "Downloading $f …"
    curl -fsSL "$BASE/$f" -o "$INSTALL_DIR/$f"
done

for asset in mic_on.svg mic_off.svg; do
    info "Downloading assets/$asset …"
    curl -fsSL "$BASE/assets/$asset" -o "$INSTALL_DIR/assets/$asset"
done

chmod +x "$INSTALL_DIR/build_app.sh"
success "Files downloaded to $INSTALL_DIR"

# ── 5. Python dependencies ────────────────────────────────────────────────────
header "Step 5 — Python dependencies"
info "Installing packages (torch + whisper may take a few minutes) …"
"$PYTHON" -m pip install --upgrade pip --quiet
"$PYTHON" -m pip install \
    rumps pynput sounddevice numpy \
    openai-whisper \
    pyobjc-core pyobjc-framework-Cocoa pyobjc-framework-Quartz \
    pyperclip cairosvg \
    --quiet
success "Dependencies installed."

# ── 6. Build & install Chatty.app ─────────────────────────────────────────────
header "Step 6 — Build Chatty.app"
bash "$INSTALL_DIR/build_app.sh" --python "$PYTHON" --source "$INSTALL_DIR"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}✅  Chatty is installed!${NC}"
echo ""
echo "  Launch:  ⌘ Space → type 'Chatty' → Enter"
echo "  Use:     Press Cmd+Shift+Space to start / stop dictation"
echo ""
echo -e "${YELLOW}First launch:${NC} macOS will ask for Accessibility + Microphone permissions."
echo "  Go to System Settings → Privacy & Security and enable both for Chatty."
echo ""
