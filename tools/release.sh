#!/usr/bin/env bash
# Build release artifacts into OUTDIR (run inside `nix develop`):
#   ff-expander-VERSION-{tx,rx}.bin          firmware, flash at 0x0
#   ff-expander-VERSION-{tx,rx}-gerbers.zip  gerbers + drill files
# Usage: tools/release.sh VERSION OUTDIR
set -euo pipefail
version=${1:?usage: release.sh VERSION OUTDIR}
outdir=$(realpath -m "${2:?usage: release.sh VERSION OUTDIR}")
cd "$(dirname "$0")/.."
mkdir -p "$outdir"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

echo "== firmware"
pio run -e tx -e rx
for env in tx rx; do
    b=.pio/build/$env
    pio pkg exec -p tool-esptool -- esptool --chip esp32c6 merge-bin \
        -o "$outdir/ff-expander-$version-$env.bin" \
        0x0 "$b/bootloader.bin" 0x8000 "$b/partitions.bin" 0x10000 "$b/firmware.bin"
done

echo "== gerbers"
layers=F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts
for board in tx rx; do
    pcb=hardware/$board/ff-expander-$board.kicad_pcb
    dir=$work/ff-expander-$version-$board-gerbers
    mkdir -p "$dir"
    kicad-cli pcb export gerbers --layers "$layers" --subtract-soldermask -o "$dir/" "$pcb"
    kicad-cli pcb export drill --format excellon --generate-map --map-format gerberx2 -o "$dir/" "$pcb"
    (cd "$dir" && python3 -m zipfile -c "$outdir/$(basename "$dir").zip" ./*)
done

echo "== artifacts"
ls -l "$outdir"
