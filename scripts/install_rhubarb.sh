#!/usr/bin/env bash
# Downloads Rhubarb Lip Sync (MIT, https://github.com/DanielSWolf/rhubarb-lip-sync) into tools/rhubarb/.
# make.py finds it there automatically. Windows: download the Windows zip from the releases page and
# unzip it into tools/rhubarb/ yourself (or set RHUBARB_PATH to rhubarb.exe).
set -euo pipefail
VER=1.13.0
cd "$(dirname "$0")/.."
case "$(uname -s)" in
  Darwin) OS=macOS ;;
  Linux) OS=Linux ;;
  *) echo "Unsupported OS: grab a build from https://github.com/DanielSWolf/rhubarb-lip-sync/releases"; exit 1 ;;
esac
ZIP="Rhubarb-Lip-Sync-$VER-$OS.zip"
mkdir -p tools/rhubarb
curl -fL -o "tools/rhubarb/$ZIP" "https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v$VER/$ZIP"
unzip -oq "tools/rhubarb/$ZIP" -d tools/rhubarb
rm "tools/rhubarb/$ZIP"
BIN="$(find tools/rhubarb -type f -name rhubarb | head -1)"
chmod +x "$BIN"
if [ "$OS" = macOS ]; then
  xattr -dr com.apple.quarantine tools/rhubarb 2>/dev/null || true   # let macOS run the downloaded binary
fi
"$BIN" --version
echo "Installed: $BIN"
