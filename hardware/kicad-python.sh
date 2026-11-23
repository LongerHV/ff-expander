#!/bin/sh
# SPDX-License-Identifier: MIT
# Run Python with KiCad's `pcbnew` module available.
# System KiCad: uses python3 if it can import pcbnew.
# Nix: run inside `nix shell nixpkgs#kicad-small nixpkgs#freerouting`.
if python3 -c "import pcbnew" 2>/dev/null; then exec python3 "$@"; fi
CLI=$(command -v kicad-cli) || { echo "kicad-cli not found" >&2; exit 1; }
OUT=$(dirname "$(dirname "$(readlink -f "$CLI")")")
CLOSURE=$(nix-store -qR "$OUT")
PY=$(echo "$CLOSURE" | grep -E 'python3-[0-9.]+-env$' | head -1)
BASE=$(echo "$CLOSURE" | grep -E 'kicad-base' | head -1)
SITE=$(ls -d "$BASE"/lib/python3*/site-packages | head -1)
PYTHONPATH="$SITE${PYTHONPATH:+:$PYTHONPATH}" exec "$PY/bin/python3" "$@"
