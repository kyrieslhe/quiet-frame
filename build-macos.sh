#!/bin/sh
set -e
cd "$(dirname "$0")"
QF_BUILD_ROOT="$(pwd)"
.venv/bin/python -m PyInstaller desktop.py --noconfirm --windowed \
  --name '留影' --osx-bundle-identifier org.quietframe.desktop \
  --icon "$QF_BUILD_ROOT/assets/QuietFrame.icns" \
  --add-data "$QF_BUILD_ROOT/static:static" \
  --add-data "$QF_BUILD_ROOT/LICENSE:." \
  --add-data "$QF_BUILD_ROOT/THIRD_PARTY_NOTICES.md:." \
  --collect-data webview --hidden-import webview.platforms.cocoa \
  --exclude-module playwright --exclude-module tkinter \
  --distpath "$QF_BUILD_ROOT/dist" --workpath "$QF_BUILD_ROOT/.build" \
  --specpath "$QF_BUILD_ROOT/.build"
