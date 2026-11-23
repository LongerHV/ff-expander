{ pkgs, ... }:

pkgs.mkShell {
  packages = with pkgs;[
    platformio
    (python3.withPackages (ps: [ ps.pyserial ]))
    openocd
    clang-tools
    linuxConsoleTools
  ];
}
