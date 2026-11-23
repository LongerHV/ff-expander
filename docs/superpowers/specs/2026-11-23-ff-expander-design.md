# ff-expander — design

## Intent

Make the ffbeast steering wheel's buttons wireless. Two Seeed XIAO ESP32-C6
boards talk over ESP-NOW: the **transmitter** (TX) sits in the wheel on a
1000 mAh LiPo and reads the buttons; the **receiver** (RX) sits in the base,
powered by the base supply, and presents button state on 74HC165 parallel
inputs. The base's MKS XDRIVE MINI reads the 165 chain over SPI exactly as it
would a wired button box.

## Goals

- Low latency: a press should reach the 165 inputs within a few ms.
- Battery lasts well beyond a 2–3 h session on 1000 mAh.
- Never leave a button "stuck" pressed when the link drops.
- Firmware built with PlatformIO; testable without buttons or registers attached.

## Non-goals (for now)

- More than 10 buttons (16 would need shift registers on both boards; possible later).
- Battery level reporting, pairing UI, encryption, multiple wheels.

## Anti-goals

- Noticeable shift-paddle lag, or lag spikes from radio power saving.
- A dropped link that keeps a button asserted.

## Approaches considered

- **ESP-IDF on the official PlatformIO espressif32 platform — chosen.** First-class
  ESP-NOW, direct control of WiFi power-save, PHY rate, GPIO wake.
- Arduino core 3.x via the `pioarduino` fork — shorter code, but relies on a
  community fork and still needs IDF calls for the parts that matter.
- Zephyr — supports the C6 and has an ESP-NOW sample, but cannot be built with
  PlatformIO on espressif32 and its ESP-NOW / power layers are thinner.
- Emulating the 165 chain with the C6 SPI slave (no chips) — rejected: real
  165s keep the XDRIVE's read timing independent of the ESP.

## Hardware

Pin map (XIAO pad → GPIO): D0=0, D1=1, D2=2, D3=21, D4=22, D5=23, D6=16,
D7=17, D8=19, D9=20, D10=18. On-board: GPIO3 = RF switch enable (drive low),
GPIO14 = antenna select (low = on-board antenna), GPIO15 = user LED (active low).

**TX (wheel):** buttons 0–9 on D1–D10, each wired to GND, internal pull-ups.
D0 is kept free (it is one of the few ADC pins) for a future battery-voltage
divider. D1/D2 (GPIO1/2) are LP GPIOs and therefore the deep-sleep wake buttons.

**RX (base):** button outputs 0–9 on D0–D9 → 165 parallel inputs (chip 1 A–H =
buttons 0–7, chip 2 A–B = buttons 8–9; unused 165 inputs tied to the
"released" level). D10 free. The 165s must run at 3.3 V (ESP outputs are 3.3 V;
74HC at 5 V would be marginal). Output polarity is a build option, default
**pressed = low** (like a pull-up button box); released is the failsafe level.

Console on both boards is the built-in USB Serial/JTAG, so D6/D7 (UART0) are
free for I/O.

## Firmware

One PlatformIO project, two environments `tx` and `rx` (role chosen with a
build flag), plus a `native` environment for unit tests. Hardware-independent
logic lives in `lib/ffx_core` (plain C): packet encode/decode, debouncer,
link watchdog.

- **Pairing:** fixed. Both MAC addresses live in a config header; each board
  adds the other as its only ESP-NOW peer and ignores packets from anyone else.
- **Radio:** WiFi STA mode, no AP, fixed channel (1), `WIFI_PS_NONE` (no modem
  sleep — it would add 10–100 ms), unicast so the MAC layer ACKs and retries.
- **Packet:** magic, version, sequence number, 16-bit button mask (10 used).
- **TX loop (1 kHz):** sample buttons, debounce, send immediately on any change,
  otherwise send a heartbeat every 20 ms.
- **Debounce:** eager — a change is reported on its first edge, then that button
  is locked for 5 ms. Lowest latency; immune to contact bounce.
- **RX:** on each valid packet, write all outputs at once (single GPIO register
  write, so the XDRIVE never latches a half-updated state). If no packet for
  100 ms → all buttons released, LED off. LED on while the link is up.
- **TX idle sleep:** no button change for 10 min → deep sleep; any press on
  D1/D2 wakes it. Expected awake current ≈ 80–100 mA → ~8–10 h per charge.

## Testing without hardware

- TX accepts serial commands that inject simulated presses (OR-ed with the real
  pins): press/release a button, set a whole mask.
- RX logs every output change and periodic link stats (packets/s, lost
  packets by sequence gaps, link up/down).
- A Python script drives both USB ports: checks every button arrives, measures
  host-observed press→output latency, resets the TX to verify the failsafe
  releases everything, and reports packet loss.

## Left to the builder

Exact ESP-NOW PHY rate, logging format, test-script details, module layout
inside `src/`.
