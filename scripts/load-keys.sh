#!/usr/bin/env bash
# Restore secret key files to /tmp from the persistent ~/.config/mcp-governance store.
# Run this once per shell/reboot before starting the resolver or streamlit.
set -euo pipefail
SRC="$HOME/.config/mcp-governance"
for f in apim-master-key.txt aisearch-key.txt; do
  if [[ -f "$SRC/$f" ]]; then
    install -m 600 "$SRC/$f" "/tmp/$f"
    echo "ok  /tmp/$f"
  else
    echo "missing $SRC/$f" >&2
  fi
done
