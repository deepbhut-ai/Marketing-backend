#!/usr/bin/env bash
# ============================================================
#  Build AutoSocial AI Agent .app + .dmg for macOS
#
#  Usage:  ./build_agent_mac.sh
#
#  Output:
#    dist/AutoSocialAgent.app   (macOS app bundle)
#    dist/AutoSocialAgent.dmg   (distributable disk image)
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"

echo ""
echo "========================================"
echo "  Building AutoSocial AI Agent (macOS)"
echo "========================================"
echo ""

# ── Activate venv ──────────────────────────────────────────────────
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[ERROR] Virtualenv not found at $VENV_DIR"
    echo "        Create it first:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

PYTHON="$VENV_DIR/bin/python"

# Ensure PyInstaller is installed
if ! "$PYTHON" -c "import PyInstaller" 2>/dev/null; then
    echo "[INFO] Installing PyInstaller..."
    "$VENV_DIR/bin/pip" install pyinstaller
fi

# ── Clean previous builds ──────────────────────────────────────────
rm -rf build dist

# ── Build .app with PyInstaller ────────────────────────────────────
echo "[INFO] Building .app bundle..."
"$PYTHON" -m PyInstaller agent_build_mac.spec --clean --noconfirm

APP_PATH="dist/AutoSocialAgent.app"
if [ ! -d "$APP_PATH" ]; then
    echo "[ERROR] Build failed — $APP_PATH not found"
    exit 1
fi

echo ""
echo "[OK] App bundle created: $APP_PATH"

# ── Build .dmg ─────────────────────────────────────────────────────
DMG_PATH="dist/AutoSocialAgent.dmg"
DMG_NAME="AutoSocialAgent"

echo "[INFO] Building .dmg..."

# Remove any previous dmg
rm -f "$DMG_PATH"

# Create a temporary DMG staging folder
STAGING="/tmp/_autosocial_dmg_staging"
rm -rf "$STAGING"
mkdir -p "$STAGING"

# Copy the .app into the staging folder
cp -R "$APP_PATH" "$STAGING/"

# Add a symlink to /Applications so users can drag-to-install
ln -s /Applications "$STAGING/Applications"

# Create the DMG from the staging folder
hdiutil create \
    -volname "$DMG_NAME" \
    -srcfolder "$STAGING" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

# Clean up staging
rm -rf "$STAGING"

if [ ! -f "$DMG_PATH" ]; then
    echo "[ERROR] DMG creation failed — $DMG_PATH not found"
    exit 1
fi

echo ""
echo "========================================"
echo "  Build complete!"
echo "========================================"
echo ""
echo "  App:    $APP_PATH"
echo "  DMG:    $DMG_PATH"
echo ""
echo "  Note: The .dmg is unsigned. To distribute, sign it with:"
echo "    codesign --force --deep --sign \"Developer ID Application: YOUR NAME\" \"$DMG_PATH\""
echo ""