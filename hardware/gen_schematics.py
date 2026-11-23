#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the ff-expander KiCad schematics (rx/ and tx/).

Every connection is a short wire stub from a pin to a net label or power
symbol, so the netlist is defined entirely by the tables below.

Usage: python3 gen_schematics.py   (e.g. `nix shell nixpkgs#kicad-small -c python3 gen_schematics.py`)
The stock KiCad symbol libraries are found automatically; override with KICAD_SYMBOL_DIR.
"""
import json
import math
import os
import re
import shutil
import sys
import uuid as uuidlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sexpr  # noqa: E402
from sexpr import Q  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OWN_LIB = os.path.join(HERE, "lib", "ff-expander.kicad_sym")
LOCAL_LIBS = {"ff-expander": OWN_LIB}
XIAO = "ff-expander:XIAO_ESP32C6"
XIAO_FP = "ff-expander:XIAO_ESP32C6_HandSolder"
XH = {2: "B2B", 6: "B6B", 11: "B11B"}
DEFAULT_FP = {
    "Device:R": "Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder",
    "Device:C": "Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder",
    "74xx:74HC165": "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm",
    "Diode:SS14": "Diode_SMD:D_SMA_Handsoldering",
}
for _n, _p in XH.items():
    DEFAULT_FP["Connector_Generic:Conn_01x%02d" % _n] = \
        "Connector_JST:JST_XH_%s-XH-A_1x%02d_P2.50mm_Vertical" % (_p, _n)
POWER_NETS = {"GND": "power:GND", "+3V3": "power:+3V3", "+5V": "power:+5V"}
STUB = 2.54
FONT = [["font", ["size", "1.27", "1.27"]]]

REPO = "https://github.com/LongerHV/ff-expander"
NOTICE = "(c) 2026 Michal Mieszczak. CERN-OHL-S-2.0. Source: " + REPO

_ns = uuidlib.UUID("6f1c3c56-1d1a-4d7e-9a43-ffe0ffe0ffe0")


def fmt(v):
    v = round(v, 4)
    return str(int(v)) if v == int(v) else repr(v)


def xiao_symbol(battery=True):
    """Our own XIAO ESP32-C6 symbol: 1-14 castellated edge pins, 23/24 the
    battery pads on the underside (same numbering as Seeed's footprint). The
    underside JTAG/boot pads (15-22) are omitted: not hand-solderable.
    battery=False: variant without 23/24, for boards powered from 5 V."""
    eff = lambda: ["effects"] + FONT  # noqa: E731
    hidden = lambda: ["effects"] + FONT + [["hide", "yes"]]  # noqa: E731

    def pin(num, name, kind, x, y, a):
        return ["pin", kind, "line", ["at", fmt(x), fmt(y), str(a)], ["length", "2.54"],
                ["name", Q(name), eff()], ["number", Q(str(num)), eff()]]

    pins = []
    left = ["D0", "D1", "D2", "D3", "D4", "D5", "D6"]  # pins 1..7, top to bottom
    for i, n in enumerate(left):
        pins.append(pin(i + 1, n, "bidirectional", -15.24, -2.54 * i, 0))
    right = [(14, "VBUS", "passive"), (13, "GND", "power_in"), (12, "3V3", "power_out"),
             (11, "D10", "bidirectional"), (10, "D9", "bidirectional"), (9, "D8", "bidirectional"),
             (8, "D7", "bidirectional")]
    for i, (num, n, kind) in enumerate(right):
        pins.append(pin(num, n, kind, 15.24, -2.54 * i, 180))
    if battery:
        pins.append(pin(23, "VBAT", "passive", -2.54, -22.86, 90))
        pins.append(pin(24, "GND", "power_in", 2.54, -22.86, 90))
    name = "XIAO_ESP32C6" + ("" if battery else "_NoBat")
    bottom = "-20.32" if battery else "-17.78"
    sym = ["symbol", Q(name), ["pin_names", ["offset", "1.016"]], ["exclude_from_sim", "no"],
           ["in_bom", "yes"], ["on_board", "yes"],
           ["property", Q("Reference"), Q("U"), ["at", "-12.7", "3.81", "0"], eff()],
           ["property", Q("Value"), Q("XIAO-ESP32-C6"), ["at", "0", "-25.4", "0"], eff()],
           ["property", Q("Footprint"), Q(XIAO_FP + ("" if battery else "_NoBat")), ["at", "0", "0", "0"], hidden()],
           ["property", Q("Datasheet"), Q("https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/"),
            ["at", "0", "0", "0"], hidden()],
           ["property", Q("Description"), Q("Seeed Studio XIAO ESP32-C6, castellated" +
                                           ("; battery pads 23/24 on the underside" if battery else
                                            "; battery pads unused")),
            ["at", "0", "0", "0"], hidden()],
           ["symbol", Q(name + "_0_1"),
            ["rectangle", ["start", "-12.7", "2.54"], ["end", "12.7", bottom],
             ["stroke", ["width", "0.254"], ["type", "default"]], ["fill", ["type", "background"]]]],
           ["symbol", Q(name + "_1_1")] + pins]
    return sym


def symbol_lib():
    return ["kicad_symbol_lib", ["version", "20231120"], ["generator", Q("ffx_gen_schematics")],
            ["generator_version", Q("1.0")], xiao_symbol(True), xiao_symbol(False)]


def _find_symdir():
    """Locate the stock symbol libraries (system install or the nix kicad wrapper)."""
    for d in ("/usr/share/kicad/symbols", "/usr/local/share/kicad/symbols",
              "/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"):
        if os.path.isdir(d):
            return d
    cli = shutil.which("kicad-cli")
    if cli:
        try:
            m = re.search(r"(/nix/store/[^'\":\s]*kicad-symbols[^'\":\s]*/share/kicad/symbols)", open(cli).read())
            if m:
                return m.group(1)
        except (OSError, UnicodeDecodeError):
            pass
    return None


class Libs:
    def __init__(self):
        self.symdir = os.environ.get("KICAD_SYMBOL_DIR") or os.environ.get("KICAD10_SYMBOL_DIR") or _find_symdir()
        if not self.symdir:
            sys.exit("KiCad symbol libraries not found: set KICAD_SYMBOL_DIR")
        self.cache = {}

    def _lib(self, nick):
        if nick not in self.cache:
            path = LOCAL_LIBS.get(nick) or os.path.join(self.symdir, nick + ".kicad_sym")
            root = sexpr.parse(open(path).read())
            self.cache[nick] = {s[1]: s for s in sexpr.find(root, "symbol")}
        return self.cache[nick]

    def get(self, lib_id):
        """Return the flattened symbol, named with its full lib_id."""
        nick, name = lib_id.split(":")
        lib = self._lib(nick)
        sym = lib[name]
        ext = sexpr.find(sym, "extends")
        if ext:
            parent = self.get(nick + ":" + ext[0][1])
            pname = ext[0][1]
            props = {p[1]: p for p in sexpr.find(sym, "property")}
            body = []
            for c in parent[2:]:
                if isinstance(c, list) and c[0] == "property" and c[1] in props:
                    body.append(props.pop(c[1]))
                elif isinstance(c, list) and c[0] == "symbol":
                    body.append([c[0], Q(c[1].replace(pname, name, 1))] + c[2:])
                else:
                    body.append(c)
            body += list(props.values())
            return ["symbol", Q(lib_id)] + body
        return ["symbol", Q(lib_id)] + sym[2:]

    def pins(self, lib_id):
        out = {}

        def walk(n):
            for c in n:
                if isinstance(c, list):
                    if c[0] == "pin":
                        at = sexpr.find(c, "at")[0]
                        num = sexpr.find(c, "number")[0][1]
                        out.setdefault(num, (float(at[1]), float(at[2]), float(at[3])))
                    else:
                        walk(c)

        walk(self.get(lib_id))
        return out

    def prop_offsets(self, lib_id):
        return {p[1]: (float(sexpr.find(p, "at")[0][1]), float(sexpr.find(p, "at")[0][2]))
                for p in sexpr.find(self.get(lib_id), "property")}


def rot(vx, vy, deg):
    """Rotate a screen-space (y down) vector counter-clockwise as seen on screen."""
    a = math.radians(deg)
    c, s = round(math.cos(a)), round(math.sin(a))
    return vx * c + vy * s, -vx * s + vy * c


class Part:
    def __init__(self, sheet, lib_id, ref, value, x, y, r):
        self.sheet, self.lib_id, self.ref, self.value = sheet, lib_id, ref, value
        self.x, self.y, self.r = x, y, r

    def pin(self, num):
        px, py, pa = self.sheet.libs.pins(self.lib_id)[str(num)]
        dx, dy = rot(px, -py, self.r)
        # pin angle points from the tip towards the body; outward is the opposite
        ox, oy = rot(-math.cos(math.radians(pa)), math.sin(math.radians(pa)), self.r)
        return self.x + dx, self.y + dy, round(ox), round(oy)


class Sheet:
    def __init__(self, libs, project, title, comments):
        self.libs, self.project = libs, project
        self.title, self.comments = title, comments
        self.items, self.used, self.pwr_n = [], [], 0
        self.uuid = self.mkuuid("sheet")

    def mkuuid(self, *key):
        return Q(str(uuidlib.uuid5(_ns, "/".join((self.project,) + tuple(str(k) for k in key)))))

    def _use(self, lib_id):
        if lib_id not in self.used:
            self.used.append(lib_id)

    def place(self, lib_id, ref, value, x, y, r=0, dnp=False, footprint="", hide_value=False, fields=(),
              ref_at=None, val_at=None, in_bom=True):
        self._use(lib_id)
        footprint = footprint or DEFAULT_FP.get(lib_id, "")
        p = Part(self, lib_id, ref, value, x, y, r)
        offs = self.libs.prop_offsets(lib_id)
        is_passive = lib_id in ("Device:R", "Device:C")

        def prop(name, val, at=None, hide=False, justify=None):
            eff = ["effects"] + FONT
            if justify:
                eff.append(["justify", justify])
            if hide:
                eff.append(["hide", "yes"])
            if at is None:
                ox, oy = offs.get(name, (0, 0))
                dx, dy = rot(ox, -oy, r)
                at = (x + dx, y + dy)
            return ["property", Q(name), Q(val), ["at", fmt(at[0]), fmt(at[1]), "90" if r % 180 else "0"], eff]

        if is_passive and r in (0, 180):
            pref = prop("Reference", ref, (x + 2.54, y - 1.27), justify="left")
            pval = prop("Value", value, (x + 2.54, y + 1.27), justify="left")
        elif is_passive:
            pref = prop("Reference", ref, (x, y - 2.54))
            pval = prop("Value", value, (x, y + 2.54))
        else:
            pref = prop("Reference", ref, ref_at, hide=ref.startswith("#"))
            pval = prop("Value", value, val_at, hide=hide_value)
        node = ["symbol", ["lib_id", Q(lib_id)], ["at", fmt(x), fmt(y), str(r)], ["unit", "1"],
                ["exclude_from_sim", "no"], ["in_bom", "yes" if in_bom and not ref.startswith("#") else "no"],
                ["on_board", "no" if ref.startswith("#") else "yes"], ["dnp", "yes" if dnp else "no"],
                ["uuid", self.mkuuid("sym", ref)], pref, pval,
                prop("Footprint", footprint, hide=True), prop("Datasheet", "", hide=True)]
        for k, v in fields:
            node.append(prop(k, v, (x, y), hide=True))
        for num in self.libs.pins(lib_id):
            node.append(["pin", Q(num), ["uuid", self.mkuuid("pin", ref, num)]])
        node.append(["instances", ["project", Q(self.project),
                                   ["path", Q("/" + self.uuid), ["reference", Q(ref)], ["unit", "1"]]]])
        self.items.append(node)
        return p

    def wire(self, x1, y1, x2, y2):
        self.items.append(["wire", ["pts", ["xy", fmt(x1), fmt(y1)], ["xy", fmt(x2), fmt(y2)]],
                           ["stroke", ["width", "0"], ["type", "default"]],
                           ["uuid", self.mkuuid("wire", x1, y1, x2, y2)]])

    def net(self, part, pin, name, stub=STUB, natural=False):
        """Stub from the pin, then a label or power symbol.

        natural=True points a power symbol the usual way (supply up, GND down)
        instead of along the stub, which avoids crowding on dense pin rows.
        """
        x, y, ox, oy = part.pin(pin)
        ex, ey = x + ox * stub, y + oy * stub
        self.wire(x, y, ex, ey)
        if natural:
            ox, oy = (0, 1) if name == "GND" else (0, -1)
        self.attach(name, ex, ey, ox, oy)

    def junction(self, x, y):
        self.items.append(["junction", ["at", fmt(x), fmt(y)], ["diameter", "0"],
                           ["color", "0", "0", "0", "0"], ["uuid", self.mkuuid("junction", x, y)]])

    def tie(self, part, pins, name, dist):
        """Tie several same-side pins together with a vertical bus `dist` away."""
        ends = []
        for pin in pins:
            x, y, ox, oy = part.pin(pin)
            ex, ey = x + ox * dist, y + oy * dist
            self.wire(x, y, ex, ey)
            ends.append((ex, ey))
        ends.sort(key=lambda e: e[1])
        top = (ends[0][0], ends[0][1] - 5.08)
        pts = [top] + ends
        for a, b in zip(pts, pts[1:]):
            self.wire(a[0], a[1], b[0], b[1])
        for e in ends[:-1]:
            self.junction(*e)
        self.attach(name, top[0], top[1], 0, -1)

    def attach(self, name, x, y, ox, oy):
        if name in POWER_NETS:
            lib_id = POWER_NETS[name]
            if name == "GND":
                r = {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}[(ox, oy)]
            else:
                r = {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}[(ox, oy)]
            self.pwr_n += 1
            val_at = None
            if ox:  # sideways: centre the text beyond the symbol body
                d = 3.3 + 0.55 * len(name)
                val_at = (x + ox * d, y)
            self.place(lib_id, "#PWR%02d" % self.pwr_n, name, x, y, r, val_at=val_at)
        else:
            a = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}[(ox, oy)]
            just = "left" if a in (0, 90) else "right"
            self.items.append(["label", Q(name), ["at", fmt(x), fmt(y), str(a)],
                               ["effects"] + FONT + [["justify", just, "bottom"]],
                               ["uuid", self.mkuuid("label", name, x, y)]])

    def nets(self, part, mapping):
        for pin, name in mapping.items():
            if name is None:
                self.nc(part, pin)
            else:
                self.net(part, pin, name)

    def nc(self, part, pin):
        x, y, _, _ = part.pin(pin)
        self.items.append(["no_connect", ["at", fmt(x), fmt(y)], ["uuid", self.mkuuid("nc", part.ref, pin)]])

    def flag(self, name, x, y):
        """PWR_FLAG on a net (the flag's pin points down into a stub)."""
        self.pwr_n += 1
        f = self.place("power:PWR_FLAG", "#FLG%02d" % self.pwr_n, "PWR_FLAG", x, y)
        self.net(f, "1", name)

    def text(self, s, x, y, size=1.27):
        self.items.append(["text", Q(s), ["exclude_from_sim", "no"], ["at", fmt(x), fmt(y), "0"],
                           ["effects", ["font", ["size", fmt(size), fmt(size)]], ["justify", "left", "top"]],
                           ["uuid", self.mkuuid("text", s[:40], x, y)]])

    def write(self, path):
        tb = ["title_block", ["title", Q(self.title)], ["date", Q("2026-11-23")], ["rev", Q("A")],
              ["company", Q("ff-expander")]]
        # KiCad prints comment 1 at the bottom: number them so they read top-down
        for i, c in enumerate(self.comments):
            tb.append(["comment", str(len(self.comments) - i), Q(c)])
        self.text(NOTICE, 302.26, 248.92)
        doc = ["kicad_sch", ["version", "20250114"], ["generator", Q("ffx_gen_schematics")],
               ["generator_version", Q("1.0")], ["uuid", self.uuid], ["paper", Q("A3")], tb,
               ["lib_symbols"] + [self.libs.get(l) for l in self.used]]
        doc += self.items
        doc.append(["sheet_instances", ["path", Q("/"), ["page", Q("1")]]])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(sexpr.dump(doc) + "\n")
        base = os.path.splitext(path)[0]
        if not os.path.exists(base + ".kicad_pro"):  # KiCad keeps board rules here: never clobber
            with open(base + ".kicad_pro", "w") as f:
                json.dump({"meta": {"filename": os.path.basename(base) + ".kicad_pro", "version": 3}}, f, indent=2)
        with open(os.path.join(os.path.dirname(path), "sym-lib-table"), "w") as f:
            f.write('(sym_lib_table\n  (version 7)\n  (lib (name "ff-expander")(type "KiCad")'
                    '(uri "${KIPRJMOD}/../lib/ff-expander.kicad_sym")(options "")(descr "ff-expander symbols"))\n)\n')
        with open(os.path.join(os.path.dirname(path), "fp-lib-table"), "w") as f:
            f.write('(fp_lib_table\n  (version 7)\n  (lib (name "ff-expander")(type "KiCad")'
                    '(uri "${KIPRJMOD}/../lib/ff-expander.pretty")(options "")(descr "ff-expander footprints"))\n)\n')


# XIAO-ESP32-C6-SMD pin numbers
X = {"D0": 1, "D1": 2, "D2": 3, "D3": 4, "D4": 5, "D5": 6, "D6": 7, "D7": 8, "D8": 9, "D9": 10,
     "D10": 11, "3V3": 12, "GND": 13, "VBUS": 14, "VBAT": 23, "GND3": 24}
# 74HC165 pin numbers for parallel inputs A..H (= D0..D7)
HC165_IN = [11, 12, 13, 14, 3, 4, 5, 6]


def build_rx(libs):
    s = Sheet(libs, "ff-expander-rx", "ff-expander RX (base)",
              ["Failsafe: pull-ups hold every 165 input 'released' (high) unless the ESP drives it.",
               "165s + pull-ups run from the XDRIVE 3.3 V, so a dead XIAO reads as 'all released'.",
               "XIAO runs from the XDRIVE 5 V via D1. 1k series resistors limit back-powering.",
               "D6 (GPIO16, UART0 TX, toggled by boot ROM) is NOT used; button 6 is on D10."])

    # --- power: XDRIVE 5 V -> Schottky -> XIAO VBUS -------------------------
    j2 = s.place("Connector_Generic:Conn_01x02", "J2", "XDRIVE_5V", 30.48, 40.64)
    s.nets(j2, {"1": "+5V_XD", "2": "GND"})
    d1 = s.place("Diode:SS14", "D1", "SS14", 63.5, 40.64, r=180)
    s.nets(d1, {"2": "+5V_XD", "1": "+5V"})
    s.text("5 V from the XDRIVE's 5 V connector (needs ~100 mA avg, ~300 mA peaks).\n"
           "D1 stops back-feeding the PC when USB is plugged in while the base is on.\n"
           "J2 pin order: match the XDRIVE 5 V connector.", 22.86, 53.34)
    c1 = s.place("Device:C", "C1", "22u", 30.48, 78.74)
    s.nets(c1, {"1": "+5V", "2": "GND"})
    c2 = s.place("Device:C", "C2", "100n", 45.72, 78.74)
    s.nets(c2, {"1": "+5V", "2": "GND"})
    s.flag("GND", 63.5, 73.66)
    s.flag("+5V", 73.66, 73.66)

    # --- XIAO --------------------------------------------------------------
    u3 = s.place(XIAO + "_NoBat", "U3", "XIAO-ESP32-C6", 50.8, 132.08, footprint=XIAO_FP + "_NoBat",
                 ref_at=(35.56, 157.48), val_at=(35.56, 160.02))
    out_pin = ["D0", "D1", "D2", "D3", "D4", "D5", "D10", "D7", "D8", "D9"]  # button n -> pad
    s.nets(u3, {X[p]: "OUT%d" % n for n, p in enumerate(out_pin)})
    s.nets(u3, {X["D6"]: None, X["3V3"]: None})
    s.net(u3, X["VBUS"], "+5V")
    s.net(u3, X["GND"], "GND")

    # --- per-button: 1k series + 10k pull-up --------------------------------
    for n in range(10):
        x = 127 + n * 12.7
        r_pu = s.place("Device:R", "R%d" % (1 + n), "10k", x, 63.5)
        s.nets(r_pu, {"1": "+3V3", "2": "BTN%d" % n})
        r_s = s.place("Device:R", "R%d" % (11 + n), "1k", x, 99.06)
        s.nets(r_s, {"1": "OUT%d" % n, "2": "BTN%d" % n})
    s.text("Per button n: XIAO OUTn -> 1k -> BTNn -> 165 input; 10k pull-up BTNn -> +3V3 (XDRIVE rail).\n"
           "Pressed = low (ESP drives low), released = high (ESP drives high or lets go).",
           124.46, 114.3)

    # --- shift registers ----------------------------------------------------
    u1 = s.place("74xx:74HC165", "U1", "74HC165", 279.4, 114.3, val_at=(292.1, 142.24))
    s.nets(u1, {HC165_IN[i]: "BTN%d" % i for i in range(8)})
    s.nets(u1, {1: "LATCH", 2: "SCK", 10: "CHAIN", 9: "MISO_165", 7: None, 8: "GND", 16: "+3V3"})
    s.net(u1, 15, "GND", natural=True)
    u2 = s.place("74xx:74HC165", "U2", "74HC165", 279.4, 190.5, val_at=(292.1, 218.44))
    s.nets(u2, {HC165_IN[0]: "BTN8", HC165_IN[1]: "BTN9"})
    s.tie(u2, [10] + HC165_IN[2:], "+3V3", 12.7)
    s.nets(u2, {1: "LATCH", 2: "SCK", 9: "CHAIN", 7: None, 8: "GND", 16: "+3V3"})
    s.net(u2, 15, "GND", natural=True)
    c3 = s.place("Device:C", "C3", "10u", 320.04, 63.5)
    s.nets(c3, {"1": "+3V3", "2": "GND"})
    c4 = s.place("Device:C", "C4", "100n", 332.74, 63.5)
    s.nets(c4, {"1": "+3V3", "2": "GND"})
    c5 = s.place("Device:C", "C5", "100n", 345.44, 63.5)
    s.nets(c5, {"1": "+3V3", "2": "GND"})
    s.text("C4 at U1, C5 at U2 (pin 16 -> pin 8, as close as possible).\nC3 where +3V3 enters the board.",
           317.5, 76.2)

    for i in range(4):
        s.place("Mechanical:MountingHole", "H%d" % (i + 1), "M2", 297.18 + i * 12.7, 236.22,
                footprint="MountingHole:MountingHole_2.2mm_M2", in_bom=False)

    # --- XDRIVE header ------------------------------------------------------
    r21 = s.place("Device:R", "R21", "47", 345.44, 114.3, r=90)
    s.nets(r21, {"1": "MISO_165", "2": "MISO"})
    j1 = s.place("Connector_Generic:Conn_01x06", "J1", "XDRIVE_SPI", 393.7, 114.3)
    s.nets(j1, {"1": "GND", "2": None, "3": "MISO", "4": "SCK", "5": "LATCH", "6": "+3V3"})
    s.flag("+3V3", 365.76, 99.06)
    s.text("J1 = XDRIVE header [GND MOSI MISO SCK GPIO_6 3.3V].\n"
           "MOSI unused. GPIO_6 = LATCH: ffbeast pulses it to load\n"
           "the 165s (SH/~LD). Check bit order on the bench:\n"
           "U1.Q7 = input H = button 7 shifts out first.", 345.44, 134.62)
    s.text("Shift order: U2.Q7 -> U1.DS (CHAIN), U1.Q7 -> MISO.\nU2 inputs C..H and U2.DS tied to "
           "+3V3 = 'released'.\n74HC165 at 3.3 V is fine to ~15 MHz SCK; SN74LV165A is a pin-compatible\n"
           "faster alternative.", 317.5, 220.98)
    return s


def build_tx(libs):
    s = Sheet(libs, "ff-expander-tx", "ff-expander TX (wheel)",
              ["Buttons switch to GND. External 10k pull-ups + 10 nF filter against motor noise and",
               "eager-debounce false triggers; 1k series for ESD and to protect D6 (UART0 TX at boot).",
               "D1/D2 are the deep-sleep wake buttons (LP GPIOs).",
               "Battery sense divider (R21/R22/C11) is for future firmware: DNP for now."])

    # --- battery ------------------------------------------------------------
    j1 = s.place("Connector_Generic:Conn_01x02", "J1", "LIPO_1000mAh", 30.48, 40.64)
    s.net(j1, "1", "VBAT")
    s.net(j1, "2", "GND")
    s.flag("GND", 86.36, 33.02)
    s.flag("VBAT", 99.06, 33.02)
    s.text("Protected 1S LiPo (PCM), JST XH. Check polarity: lead colours\nare not standard. "
           "No power switch: idle -> deep sleep.\n"
           "U1 pads 23/24 (VBAT/GND) are under the module: give them\n"
           "plated holes in the PCB so they can be soldered from the back.", 22.86, 50.8)

    # --- XIAO --------------------------------------------------------------
    u1 = s.place(XIAO, "U1", "XIAO-ESP32-C6", 50.8, 132.08, footprint=XIAO_FP,
                 ref_at=(35.56, 157.48), val_at=(35.56, 160.02))
    btn_pin = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10"]  # button n -> pad
    s.nets(u1, {X[p]: "BTN%d" % n for n, p in enumerate(btn_pin)})
    s.nets(u1, {X["D0"]: "VBAT_SENSE", X["VBUS"]: None, X["GND3"]: "GND", X["VBAT"]: "VBAT"})
    s.net(u1, X["GND"], "GND")
    s.net(u1, X["3V3"], "+3V3")

    # --- battery sense (future) --------------------------------------------
    r21 = s.place("Device:R", "R21", "470k", 30.48, 190.5, dnp=True)
    s.nets(r21, {"1": "VBAT", "2": "VBAT_SENSE"})
    r22 = s.place("Device:R", "R22", "470k", 45.72, 190.5, dnp=True)
    s.nets(r22, {"1": "VBAT_SENSE", "2": "GND"})
    c11 = s.place("Device:C", "C11", "100n", 60.96, 190.5, dnp=True)
    s.nets(c11, {"1": "VBAT_SENSE", "2": "GND"})
    s.text("VBAT/2 into the ADC on D0 (4.2 V -> 2.1 V), ~4 uA.\nC11 gives the ADC a low-impedance source.",
           25.4, 213.36)

    # --- per-button: 10k pull-up, 10 nF, 1k series ---------------------------
    for n in range(10):
        x = 127 + n * 15.24
        r_pu = s.place("Device:R", "R%d" % (1 + n), "10k", x, 63.5)
        s.nets(r_pu, {"1": "+3V3", "2": "BTN%d" % n})
        c = s.place("Device:C", "C%d" % (1 + n), "10n", x, 91.44)
        s.nets(c, {"1": "BTN%d" % n, "2": "GND"})
        r_s = s.place("Device:R", "R%d" % (11 + n), "1k", x, 119.38)
        s.nets(r_s, {"1": "BTN%d" % n, "2": "SW%d" % n})
    s.text("Per button n: +3V3 -> 10k -> BTNn (XIAO pin) -> 10 nF -> GND;\n"
           "BTNn -> 1k -> SWn -> button -> GND. Place the RC next to the XIAO pin.",
           124.46, 134.62)

    # --- button connector ----------------------------------------------------
    j2 = s.place("Connector_Generic:Conn_01x11", "J2", "WHEEL_BUTTONS", 304.8, 81.28)
    s.nets(j2, {str(n + 1): "SW%d" % n for n in range(10)})
    s.net(j2, "11", "GND")
    for i in range(4):
        s.place("Mechanical:MountingHole", "H%d" % (i + 1), "M2", 297.18 + i * 12.7, 160.02,
                footprint="MountingHole:MountingHole_2.2mm_M2", in_bom=False)
    s.text("H1-H4: M2 mounting holes, 45 x 25 mm pattern.", 289.56, 170.18)
    s.text("Wheel buttons: each between SWn and GND.\nButtons 0/1 (D1/D2) wake the TX from deep sleep.",
           289.56, 116.84)
    return s


def main():
    with open(OWN_LIB, "w") as f:
        f.write(sexpr.dump(symbol_lib()) + "\n")
    libs = Libs()
    build_rx(libs).write(os.path.join(HERE, "rx", "ff-expander-rx.kicad_sch"))
    build_tx(libs).write(os.path.join(HERE, "tx", "ff-expander-tx.kicad_sch"))


if __name__ == "__main__":
    main()
