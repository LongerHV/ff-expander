{ pkgs, ... }:

let
  kicad = pkgs.kicad-small;
  # kicad.base ships the `pcbnew` module, built against pkgs.python3
  python = pkgs.python3.withPackages (ps: [
    ps.pyserial # tools/link_test.py
    (ps.toPythonModule kicad.base) # hardware/gen_pcb.py
  ]);
in
pkgs.mkShell {
  packages = with pkgs; [
    platformio # build, flash, unit tests (fetches its own ESP toolchain + OpenOCD)
    python
    clang-tools # clangd / clang-format for editors
    kicad # schematics/PCB editor, kicad-cli (netlist, DRC)
    freerouting # autorouter used by hardware/gen_pcb.py
  ];

  # Stock libraries for the hardware generators
  KICAD10_SYMBOL_DIR = "${kicad.libraries.symbols}/share/kicad/symbols";
  KICAD10_FOOTPRINT_DIR = "${kicad.libraries.footprints}/share/kicad/footprints";
}
