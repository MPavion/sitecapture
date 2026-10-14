#!/usr/bin/env bash
# SiteCapture - macOS build script
# Produces: dist/SiteCapture.app  +  SiteCapture.dmg
set -euo pipefail

APP_NAME="SiteCapture"
APP_VERSION="1.0.0"
DMG_NAME="${APP_NAME}.dmg"
BUNDLE="dist/${APP_NAME}.app"

echo ""
echo " ============================================"
echo "  SiteCapture  --  macOS Build Script"
echo " ============================================"
echo ""

# ── 1. Python check ────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo " [ERROR] python3 not found."
    echo ""
    echo " Install Python 3.10+ from https://www.python.org/downloads/"
    echo " or via Homebrew:  brew install python"
    exit 1
fi
PY_VER=$(python3 --version 2>&1)
echo " Found: ${PY_VER}"
echo ""

# ── 2. Virtual environment ─────────────────────────────────────────────────────
if [ -f "venv/bin/activate" ]; then
    echo " [OK] Virtual environment already exists."
else
    echo " Creating virtual environment..."
    python3 -m venv venv
    echo " [OK] Virtual environment created."
fi

# shellcheck disable=SC1091
source venv/bin/activate

# ── 3. Dependencies ────────────────────────────────────────────────────────────
echo ""
echo " [1/4]  Installing dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install pyinstaller --upgrade --quiet
echo " [OK] Dependencies ready."

# ── 4. Icon (PNG → ICNS) ───────────────────────────────────────────────────────
echo ""
echo " [2/4]  Generating icon..."
python3 make_icon.py 2>/dev/null || echo "        WARNING: make_icon.py failed — continuing without icon"

ICON_ARG=""
if [ -f "icon.png" ]; then
    ICONSET="icon.iconset"
    rm -rf "${ICONSET}"
    mkdir "${ICONSET}"

    sips -z   16   16 icon.png --out "${ICONSET}/icon_16x16.png"          &>/dev/null
    sips -z   32   32 icon.png --out "${ICONSET}/icon_16x16@2x.png"       &>/dev/null
    sips -z   32   32 icon.png --out "${ICONSET}/icon_32x32.png"          &>/dev/null
    sips -z   64   64 icon.png --out "${ICONSET}/icon_32x32@2x.png"       &>/dev/null
    sips -z  128  128 icon.png --out "${ICONSET}/icon_128x128.png"        &>/dev/null
    sips -z  256  256 icon.png --out "${ICONSET}/icon_128x128@2x.png"     &>/dev/null
    sips -z  256  256 icon.png --out "${ICONSET}/icon_256x256.png"        &>/dev/null
    sips -z  512  512 icon.png --out "${ICONSET}/icon_256x256@2x.png"     &>/dev/null
    sips -z  512  512 icon.png --out "${ICONSET}/icon_512x512.png"        &>/dev/null
    sips -z 1024 1024 icon.png --out "${ICONSET}/icon_512x512@2x.png"     &>/dev/null

    iconutil -c icns "${ICONSET}" -o icon.icns
    rm -rf "${ICONSET}"
    ICON_ARG="--icon icon.icns"
    echo " [OK] icon.icns created."
else
    echo "        WARNING: icon.png not found — building without icon."
fi

# ── 5. PyInstaller build ───────────────────────────────────────────────────────
echo ""
echo " [3/4]  Building .app bundle..."
echo ""

# shellcheck disable=SC2086
pyinstaller --noconfirm --onedir --windowed \
  --name "${APP_NAME}" \
  ${ICON_ARG} \
  --add-data "icon.ico:." \
  --collect-all customtkinter \
  --hidden-import yt_dlp \
  --hidden-import browser_cookie3 \
  --hidden-import anthropic \
  --hidden-import lxml \
  --hidden-import bs4 \
  --hidden-import PIL \
  main.py

if [ ! -d "${BUNDLE}" ]; then
    echo ""
    echo " [ERROR] PyInstaller did not produce ${BUNDLE}"
    exit 1
fi
echo ""
echo " [OK] ${BUNDLE} created."

# ── 6. DMG packaging ───────────────────────────────────────────────────────────
echo ""
echo " [4/4]  Packaging DMG..."

TMP_DMG="/tmp/${APP_NAME}-dmg-$$"
rm -rf "${TMP_DMG}"
mkdir -p "${TMP_DMG}"

cp -R "${BUNDLE}" "${TMP_DMG}/"
ln -s /Applications "${TMP_DMG}/Applications"

rm -f "${DMG_NAME}"
hdiutil create \
    -volname "${APP_NAME} ${APP_VERSION}" \
    -srcfolder "${TMP_DMG}" \
    -ov \
    -format UDZO \
    "${DMG_NAME}"

rm -rf "${TMP_DMG}"

echo ""
echo " ============================================"
echo "  Build complete!"
echo ""
echo "  App bundle : ${BUNDLE}"
echo "  Installer  : ${DMG_NAME}"
echo ""
echo "  To install: open ${DMG_NAME} and drag"
echo "  SiteCapture into Applications."
echo ""
echo "  First launch: right-click the app → Open"
echo "  (bypasses Gatekeeper for unsigned apps)."
echo " ============================================"
echo ""
