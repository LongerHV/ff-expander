# Libraries

All ours, generated, licensed CERN-OHL-S-2.0 like the rest of the hardware:

- `ff-expander.kicad_sym` — `XIAO_ESP32C6` symbol (by `../gen_schematics.py`).
  Pins 1–14 are the castellated edge, 23/24 the battery pads on the underside.
- `ff-expander.pretty/XIAO_ESP32C6_HandSolder.kicad_mod` (by
  `../gen_footprints.py`) — XIAO ESP32-C6 soldered flat by hand: castellated
  pads lengthened outwards, a slot under the battery pads with bottom-side
  bridge pads (23 VBAT, 24 GND), and copper keep-outs under the module and
  its antenna end. Drawn from the module's published dimensions.

Earlier revisions vendored Seeed Studio's OPL footprints (CC BY-SA 4.0); they
are no longer used.
