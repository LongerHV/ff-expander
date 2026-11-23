# ff-expander — hardware

Companion to `docs/superpowers/specs/2026-11-23-ff-expander-design.md`.

Known constraints: the XDRIVE button header provides **3.3 V**, its SPI bus is
**not shared**, and both enclosures are **3D-printed** (no metal), so the
on-board ceramic antennas are used on both boards.

## RX (base): XIAO → 2× 74HC165 → XDRIVE

```
                         +3V3_XD  (XDRIVE header 3.3 V)
                            │
                     10k ×10 pull-ups (or 9-pin 10k network)
                            │
XIAO out n ──[1k]───────────┴──► 165 parallel input n

U1 (74HC165): A–H = buttons 0–7     U2 (74HC165): A–B = buttons 8–9
U2 C–H ──► +3V3_XD                  U2 SER (pin 10) ──► +3V3_XD
U2 QH (pin 9) ──► U1 SER (pin 10)
U1 QH (pin 9) ──[47Ω]──► XDRIVE MISO
XDRIVE SCK   ──► CLK    (pin 2) of U1 and U2
XDRIVE latch ──► SH/LD̅  (pin 1) of U1 and U2
CLK INH (pin 15) ──► GND on U1 and U2
VCC pin 16 / GND pin 8; 100 nF at each chip; 10 µF across +3V3_XD on the board
XIAO GND ── XDRIVE GND (ground wire runs with the signal wires)
```

Why each part is there:

- **10k pull-ups to the XDRIVE rail:** while the ESP is resetting, being
  flashed, crashed or unpowered, its pins float. The pull-ups make every input
  read "released" (high). This is the failsafe in hardware.
- **165s powered from the XDRIVE, not the XIAO:** if the XIAO dies, the
  XDRIVE still reads valid chips showing "all released", not floating garbage.
- **1k series resistors (ESP → 165):** the two boards are powered separately.
  If the XIAO runs (e.g. USB while flashing) with the base off, the ESP would
  otherwise drive the unpowered 165s and XDRIVE rail through their input clamp
  diodes. 1k limits that to ~3 mA per pin. Pressed level with 10k/1k ≈ 0.3 V,
  well below 74HC V_IL at 3.3 V.
- **47 Ω on MISO:** damps ringing on the cable; place it at the 165 end.
- **Latch wiring:** a 74HC165 keeps loading while SH/LD̅ is low. Follow the
  ffbeast button-box wiring for which header pin is the latch. Verify the bit
  order and button numbering on the bench (QH = input H shifts out first).
- 74HC165 at 3.3 V is good to roughly 15 MHz of shift clock. If the XDRIVE
  clocks faster, use SN74LV165A (same pinout).

### RX power

The XDRIVE header gives only 3.3 V and its budget is unknown. The XIAO with
the radio always on averages 80–100 mA, with ~300 mA TX peaks. So **don't run
the XIAO from the header 3.3 V.** Instead:

- Use a small 5 V buck from the base supply (e.g. Traco TSR 1-2450, or a
  Pololu D24V5F5 / D36V6F5) → **SS14 Schottky** → XIAO `5V` pin.
- The diode stops back-feeding the PC when USB is plugged in at the same
  time.
- Put 10–22 µF + 100 nF at the XIAO `5V` pin.

## TX (wheel): XIAO + LiPo + 10 buttons

Per button (D1–D10):

```
3V3 ──10k──┬── GPIO
           ├── 10 nF ── GND
           └──1k── wire ── button ── GND
```

- **10k external pull-up:** the internal one (~45k) is weak. The wires run
  next to the FFB motor, and the eager debounce acts on the first edge, so
  noise would show up as phantom presses. Current only flows while a button
  is held, so this costs nothing in deep sleep. It also keeps the D1/D2 wake
  pins defined without holding the internal pull-ups during sleep.
- **10 nF:** filters spikes (τ ≈ 100 µs, invisible at a 1 kHz scan).
- **1k series:** limits ESD from fingers. It also protects D6 (GPIO16 =
  UART0 TX, which the boot ROM drives) if that button is held during boot.

Power:

- **Battery:** 1000 mAh LiPo **with a protection circuit**, wired to the
  BAT+/BAT− pads on the XIAO's underside. Check the polarity — JST lead
  colours aren't standard.
- **Switch (optional):** a slide switch in BAT+ for storage. It also prevents
  charging while off.
- **Charging:** the on-board charger runs at ~100 mA, so a full charge takes
  many hours.
- **Battery sense (future, D0):** 470k / 470k divider plus 100 nF on the ADC
  node. 4.2 V reads as 2.1 V at ~4 µA continuous draw.

## Pin-map notes for firmware

1. **RX: move output 6 from D6 to D10.** D6 = GPIO16 = UART0 TX, which the boot
   ROM drives at every reset regardless of console config, so button 6 would
   flicker pressed on every boot. New RX map:
   `{0, 1, 2, 21, 22, 23, 18, 17, 19, 20}` (D0–D5, D10, D7–D9). D6 is unused.
2. **RX:** set each output level *before* switching the pin to output.
3. **TX:** D6 stays usable thanks to the 1k series resistor. Alternative:
   permanently disable ROM logging via eFuse.
4. No D pins are strapping pins.

## BOM (beyond 2× XIAO ESP32-C6)

| Part | Qty | Where |
|---|---|---|
| 74HC165 (or SN74LV165A) | 2 | RX |
| 10k resistor (or 9-pin network + 1 discrete) | 20 | RX pull-ups, TX pull-ups |
| 1k resistor | 20 | RX series, TX series |
| 47 Ω resistor | 1 | RX MISO |
| 470k resistor | 2 | TX battery sense (future) |
| 10 nF ceramic | 10 | TX button filters |
| 100 nF ceramic | 4 | 165 decoupling, XIAO 5V, ADC node |
| 10–22 µF | 2 | RX 3.3 V rail, XIAO 5V |
| SS14 Schottky | 1 | RX 5 V feed |
| 5 V buck module | 1 | RX power |
| 1000 mAh protected LiPo | 1 | TX |
| Slide switch (optional) | 1 | TX |
