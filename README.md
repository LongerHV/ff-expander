# FF expander

ff-expander is a wireless expansion module for ffbeast based steering wheels.

Two Seeed XIAO ESP32-C6 boards linked over ESP-NOW: the **tx** board in the
wheel reads up to 10 buttons; the **rx** board in the base drives the parallel
inputs of two daisy-chained 74HC165s, which the MKS XDRIVE MINI reads over SPI.
Design notes: `docs/superpowers/specs/2026-11-23-ff-expander-design.md`.

## Wiring

| Button | TX pad (to GND) | RX pad (→ 74HC165) |
|-------:|-----------------|--------------------|
| 0 | D1 (wake) | D0 → chip 1 A |
| 1 | D2 (wake) | D1 → chip 1 B |
| 2 | D3 | D2 → chip 1 C |
| 3 | D4 | D3 → chip 1 D |
| 4 | D5 | D4 → chip 1 E |
| 5 | D6 | D5 → chip 1 F |
| 6 | D7 | D10 → chip 1 G |
| 7 | D8 | D7 → chip 1 H |
| 8 | D9 | D8 → chip 2 A |
| 9 | D10 | D9 → chip 2 B |

- TX buttons are wired between the pad and GND (internal pull-ups). D0 is free
  for a future battery-voltage divider. Buttons 0/1 wake the wheel from sleep.
- RX outputs are **low when pressed**, high when released or when the link is
  lost (`FFX_RX_PRESSED_LOW` in `include/ffx_config.h`). Tie unused 165 inputs
  high. Power the 165s from **3.3 V**.
- The RX user LED is lit while the link is up; the TX sleeps after 10 min idle.

## Build, flash, test

```sh
nix develop                 # or nix-shell
pio test -e native          # unit tests for lib/ffx_core
pio run -e tx -t upload     # wheel board
pio run -e rx -t upload     # base board
python3 tools/link_test.py  # end-to-end test with both boards on USB
```

Board MACs (pairing) and serial ports are set in `include/ffx_config.h` and
`platformio.ini`.

### Console commands

TX: `p N` / `r N` press/release simulated button N, `m MASK` set all simulated
buttons, `mute MS` stop transmitting, `s` stats, `sleep`, `reboot`.
RX: `s` link stats. RX logs every output change as `RX t=… btn=0x… link=up|down`.
