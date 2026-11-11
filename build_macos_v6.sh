#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

ICON_ARGS=()
if [[ -f "MCRDP_icon.icns" ]]; then
  ICON_ARGS=(--icon "MCRDP_icon.icns")
elif [[ -f "MCRDP_v4_icns.icns" ]]; then
  ICON_ARGS=(--icon "MCRDP_v4_icns.icns")
fi

python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name "MCRDP_v6" \
  "${ICON_ARGS[@]}" \
  --paths "src" \
  --collect-all pandas \
  --collect-all numpy \
  --collect-all openpyxl \
  --hidden-import pandas._libs._cyutility \
  --add-data "config/variables.json:config" \
  launcher.py
