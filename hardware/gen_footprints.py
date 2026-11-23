#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate ff-expander's own footprints into lib/ff-expander.pretty/.

XIAO_ESP32C6_HandSolder: Seeed XIAO ESP32-C6 soldered flat by hand.
  * Origin at module centre, USB-C towards -Y (top view, as Seeed's pinout).
  * Castellated pads lengthened outwards for iron access.
  * Slot (Edge.Cuts) under the module's battery pads; the battery is bridged
    from two bottom-side pads (23 VBAT, 24 GND) at the slot edge with short wires.
  * Copper keep-outs: no F.Cu tracks/vias/pour under the module (its underside
    has exposed pads), and nothing on either layer under the antenna end.

Dimensions from the XIAO ESP32-C6 mechanical data: 17.8 x 21 mm, 2.54 mm
pitch, battery pads 2.54 mm apart, 5.5 mm from centre towards the antenna end.
"""

import os
import sys
import uuid as uuidlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sexpr  # noqa: E402
from sexpr import Q  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "lib", "ff-expander.pretty")
_ns = uuidlib.UUID("8a1d7f2e-3b4c-4d5e-8f60-ffe0ffe0ffe1")

W, H = 17.8, 21.0  # module body
PITCH = 2.54
PAD_IN, PAD_OUT = 1.0, 1.0  # castellated pad extent inside / outside the module edge
PAD_W = 1.7
BAT_Y = 5.53  # battery pads, towards the antenna end (+Y)
BAT_X = (-1.79, 0.75)  # module's BAT+ / BAT- pads (seen through the slot)
BRIDGE_X = (-2.4, 1.4)  # our bottom pads 23 (VBAT) / 24 (GND), spread for wiring
BRIDGE_W, BRIDGE_H = 2.0, 2.0
SLOT = (-3.8, 3.3, 2.8, 7.8)  # x0, y0, x1, y1
ANT_KEEPOUT_Y0, ANT_EXT = 8.6, 4.0  # antenna keep-out from y0 to 4 mm past the module end


def f(v):
    v = round(v, 4)
    return str(int(v)) if v == int(v) else repr(v)


class FP:
    def __init__(self, name):
        self.name, self.items, self.n = name, [], 0

    def uid(self):
        self.n += 1
        return ["uuid", Q(str(uuidlib.uuid5(_ns, "%s/%d" % (self.name, self.n))))]

    def line(self, layer, x0, y0, x1, y1, w=0.12):
        self.items.append(
            [
                "fp_line",
                ["start", f(x0), f(y0)],
                ["end", f(x1), f(y1)],
                ["stroke", ["width", f(w)], ["type", "solid"]],
                ["layer", Q(layer)],
                self.uid(),
            ]
        )

    def rect(self, layer, x0, y0, x1, y1, w=0.05):
        self.items.append(
            [
                "fp_rect",
                ["start", f(x0), f(y0)],
                ["end", f(x1), f(y1)],
                ["stroke", ["width", f(w)], ["type", "solid"]],
                ["fill", "no"],
                ["layer", Q(layer)],
                self.uid(),
            ]
        )

    def text(self, layer, s, x, y, size=1.0, mirror=False):
        eff = ["effects", ["font", ["size", f(size), f(size)], ["thickness", f(size * 0.15)]]]
        if mirror:
            eff.append(["justify", "mirror"])
        self.items.append(["fp_text", "user", Q(s), ["at", f(x), f(y), "0"], ["layer", Q(layer)], self.uid(), eff])

    def pad(self, num, x, y, w, h, layers):
        self.items.append(
            [
                "pad",
                Q(num),
                "smd",
                "roundrect",
                ["at", f(x), f(y)],
                ["size", f(w), f(h)],
                ["layers"] + [Q(layer) for layer in layers],
                ["roundrect_rratio", "0.25"],
                self.uid(),
            ]
        )

    def keepout(self, layers, pts, tracks=True, vias=True, pour=True):
        na = lambda b: "not_allowed" if b else "allowed"  # noqa: E731
        self.items.append(
            [
                "zone",
                ["net", "0"],
                ["net_name", Q("")],
                ["layers"] + [Q(layer) for layer in layers],
                self.uid(),
                ["hatch", "edge", "0.5"],
                ["connect_pads", ["clearance", "0"]],
                ["min_thickness", "0.25"],
                ["filled_areas_thickness", "no"],
                [
                    "keepout",
                    ["tracks", na(tracks)],
                    ["vias", na(vias)],
                    ["pads", "allowed"],
                    ["copperpour", na(pour)],
                    ["footprints", "allowed"],
                ],
                ["fill", ["thermal_gap", "0.5"], ["thermal_bridge_width", "0.5"]],
                ["polygon", ["pts"] + [["xy", f(x), f(y)] for x, y in pts]],
            ]
        )

    def write(self, descr, tags, ref_at, attr="smd"):
        def prop(k, v, at, layer, hide=False):
            eff = ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]
            if hide:
                eff.append(["hide", "yes"])
            return ["property", Q(k), Q(v), ["at", f(at[0]), f(at[1]), "0"], ["layer", Q(layer)], self.uid(), eff]

        doc = [
            "footprint",
            Q(self.name),
            ["version", "20241229"],
            ["generator", Q("ffx_gen_footprints")],
            ["generator_version", Q("1.0")],
            ["layer", Q("F.Cu")],
            prop("Reference", "REF**", ref_at, "F.SilkS"),
            prop("Value", self.name, (0, 0), "F.Fab"),
            prop("Datasheet", "", (0, 0), "F.Fab", True),
            ["descr", Q(descr)],
            ["tags", Q(tags)],
            ["attr", attr],
        ] + self.items
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, self.name + ".kicad_mod"), "w") as fh:
            fh.write(sexpr.dump(doc) + "\n")


def xiao(battery=True):
    """battery=False: no slot / bridge pads (board powered from 5 V)."""
    fp = FP("XIAO_ESP32C6_HandSolder" + ("" if battery else "_NoBat"))
    hw, hh = W / 2, H / 2
    pad_len = PAD_IN + PAD_OUT
    pad_cx = hw + (PAD_OUT - PAD_IN) / 2
    for i in range(7):
        y = -3 * PITCH + i * PITCH
        fp.pad(str(i + 1), -pad_cx, y, pad_len, PAD_W, ["F.Cu", "F.Mask", "F.Paste"])  # D0..D6
        fp.pad(str(14 - i), pad_cx, y, pad_len, PAD_W, ["F.Cu", "F.Mask", "F.Paste"])  # VBUS..D7
    # battery bridge pads on the bottom, at the slot's inner edge
    sx0, sy0, sx1, sy1 = SLOT
    # Assembly: solder short wires to the XIAO's BAT pads first, thread them
    # through the slot, solder the module, then the wires to these pads.
    if battery:
        py = sy0 - 0.35 - BRIDGE_H / 2
        for num, x in zip(("23", "24"), BRIDGE_X, strict=True):
            fp.pad(num, x, py, BRIDGE_W, BRIDGE_H, ["B.Cu", "B.Mask"])
        fp.text("B.SilkS", "+", BRIDGE_X[0], py - BRIDGE_H / 2 - 0.9, 1.0, mirror=True)
        fp.text("B.SilkS", "-", BRIDGE_X[1], py - BRIDGE_H / 2 - 0.9, 1.0, mirror=True)
        fp.text("B.SilkS", "BAT", (BRIDGE_X[0] + BRIDGE_X[1]) / 2, py - BRIDGE_H / 2 - 0.9, 0.8, mirror=True)
        fp.rect("Edge.Cuts", sx0, sy0, sx1, sy1, 0.1)
        # no tracks/vias within 0.35 mm of the slot (autorouters don't know
        # the copper-to-edge rule); pours keep their own clearance
        m = 0.35
        fp.keepout(
            ["F.Cu", "B.Cu"],
            [(sx0 - m, sy0 - m), (sx1 + m, sy0 - m), (sx1 + m, sy1 + m), (sx0 - m, sy1 + m)],
            pour=False,
        )

    # keep-outs
    # stop short of the castellated pads so tracks can reach them
    kx = hw - PAD_IN - 0.3
    fp.keepout(["F.Cu"], [(-kx, -hh), (kx, -hh), (kx, ANT_KEEPOUT_Y0), (-kx, ANT_KEEPOUT_Y0)])
    fp.keepout(["F.Cu", "B.Cu"], [(-hw, ANT_KEEPOUT_Y0), (hw, ANT_KEEPOUT_Y0), (hw, hh + ANT_EXT), (-hw, hh + ANT_EXT)])

    # fab: body, USB-C, antenna
    fp.rect("F.Fab", -hw, -hh, hw, hh, 0.1)
    fp.rect("F.Fab", -4.5, -hh - 1.5, 4.5, -hh + 6, 0.1)
    fp.text("F.Fab", "USB-C", 0, -hh + 2, 0.8)
    fp.text("F.Fab", "ANT", 4.5, hh - 1.5, 0.8)
    fp.text("F.Fab", "${REFERENCE}", 0, 0, 1.0)
    # silk: module ends, pin-1 mark, antenna keep-out hint
    fp.line("F.SilkS", -hw + 1.2, hh, hw - 1.2, hh)
    fp.line("F.SilkS", -hw - PAD_OUT - 0.4, -3 * PITCH - 1.0, -hw - PAD_OUT - 0.4, -3 * PITCH + 1.0, 0.2)
    # courtyard: pads + USB overhang (sides kept tight for the M2 holes)
    fp.rect("F.CrtYd", -hw - PAD_OUT, -hh - 1.75, hw + PAD_OUT, hh + 0.25)
    fp.write(
        "Seeed Studio XIAO ESP32-C6, hand-soldered flat. "
        + (
            "Slot under the battery pads; bridge pads 23 (VBAT) / 24 (GND) on the bottom. "
            if battery
            else "Battery pads unused. "
        )
        + "Keep-outs under module and antenna.",
        "XIAO ESP32-C6 castellated hand-solder",
        (0, -hh - 3),
    )


if __name__ == "__main__":
    xiao(battery=True)
    xiao(battery=False)
