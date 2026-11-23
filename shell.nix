{ pkgs, ... }:

pkgs.mkShell {
  packages = with pkgs; [
    platformio # build, flash, unit tests (fetches its own ESP toolchain + OpenOCD)
    (python3.withPackages (ps: [ ps.pyserial ])) # tools/link_test.py
    clang-tools # clangd / clang-format for editors
  ];
}
