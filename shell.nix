{ pkgs, ... }:

pkgs.mkShell {
  packages = with pkgs;[
    platformio
    python3
    openocd
    clang-tools
    linuxConsoleTools
  ];
}
