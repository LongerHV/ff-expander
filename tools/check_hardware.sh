#!/usr/bin/env bash
# Hardware checks (run inside `nix develop`):
#  - footprints and schematics match their generators
#  - ERC and DRC report no errors
set -euo pipefail
cd "$(dirname "$0")/.."

out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

echo "== generators in sync"
(cd hardware && python3 gen_footprints.py >/dev/null && python3 gen_schematics.py >/dev/null)
if ! git diff --exit-code --stat -- hardware; then
    echo "hardware/ differs from its generators: run gen_footprints.py / gen_schematics.py and commit" >&2
    exit 1
fi

for board in tx rx; do
    dir=hardware/$board
    echo "== $board ERC"
    kicad-cli sch erc --severity-error --exit-code-violations -o "$out/$board-erc.rpt" \
        "$dir/ff-expander-$board.kicad_sch" >/dev/null || { cat "$out/$board-erc.rpt"; exit 1; }
    echo "== $board DRC"
    kicad-cli pcb drc --severity-error --exit-code-violations -o "$out/$board-drc.rpt" \
        "$dir/ff-expander-$board.kicad_pcb" >/dev/null || { cat "$out/$board-drc.rpt"; exit 1; }
done
echo "hardware OK"
