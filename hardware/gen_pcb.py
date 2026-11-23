#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the ff-expander PCBs (tx/ and rx/) from their schematics.

For each board: read the schematic netlist, place every footprint, draw the
outline, autoroute with Freerouting (retrying until everything is routed),
pour GND on both layers, then let KiCad refill zones and run DRC
(report: <board>/drc.rpt).

Run (needs KiCad's pcbnew module and freerouting on PATH):
    nix shell nixpkgs#kicad-small nixpkgs#freerouting -c ./kicad-python.sh gen_pcb.py [tx] [rx]
Options: --no-route  place only (keep ratsnest, no tracks)
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sexpr  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OWN_FP = {"ff-expander": os.path.join(HERE, "lib", "ff-expander.pretty")}
ORIGIN = (100.0, 80.0)     # where boards sit on the KiCad page
NOTICE = "CERN-OHL-S-2.0  github.com/LongerHV/ff-expander"
COPYRIGHT = "(c) 2026 Michal Mieszczak. CERN-OHL-S-2.0. Source: https://github.com/LongerHV/ff-expander"

mm = pcbnew.FromMM


def P(x, y):
    return pcbnew.VECTOR2I(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))


# ---- board specs ---------------------------------------------------------------
# placement: ref -> (x, y, rotation, side) in board mm; side "B" = bottom.
# texts: (string, x, y, layer, size, mirror)

class TX:
    name, title = "tx", "ff-expander TX (wheel)"
    W, H = 52.0, 32.0
    power_nets = ["GND", "+3V3", "VBAT"]

    @classmethod
    def placement(cls):
        pl = {"U1": (10.5, 16.0, 90, "F")}   # XIAO: USB-C overhangs the left edge
        for n, (x, y) in enumerate(corners(cls.W, cls.H, 3.5, 3.5)):
            pl["H%d" % (n + 1)] = (x, y, 0, "F")
        # per-button rows (top row = button 9): 10k pull-up | 10 nF | 1k series
        for n in range(10):
            y = 3.6 + 2.75 * (9 - n)
            pl["R%d" % (1 + n)] = (26.95, y, 0, "F")     # +3V3 | BTN
            pl["C%d" % (1 + n)] = (31.15, y, 0, "F")     # BTN | GND
            pl["R%d" % (11 + n)] = (35.35, y, 0, "F")    # BTN | SW
        pl["J2"] = (41.1, 28.5, 90, "F")   # buttons: pin 1 (SW0) at the bottom
        pl["J1"] = (48.0, 17.25, 90, "F")  # battery at the right edge
        # battery-sense divider (DNP) on the bottom, under the XIAO next to D0
        pl["R21"] = (6.5, 18.0, 0, "B")
        pl["R22"] = (6.5, 20.6, 0, "B")
        pl["C11"] = (6.5, 23.0, 0, "B")
        return pl

    @classmethod
    def texts(cls):
        F, B = pcbnew.F_SilkS, pcbnew.B_SilkS
        t = [(s, x, 1.3, F, 0.8, False) for x, s in ((26.95, "10k"), (31.15, "10n"), (35.35, "1k"))]
        t += [("B%d" % n, 23.6, 3.6 + 2.75 * (9 - n), F, 0.8, False) for n in range(10)]
        t += [("ff-expander TX  rev A", 31.0, 30.9, B, 0.8, True), (NOTICE, 24.0, 1.2, B, 0.8, True)]
        for k, line in enumerate(("XIAO BAT +/-: wire first,", "thread wires through slot,",
                                  "solder XIAO, then wires", "to the +/- pads here.")):
            t.append((line, 31.8, 7.0 + 1.3 * k, B, 0.8, True))
        t += [("%d" % n, 44.6, 28.5 - 2.5 * n, B, 0.8, True) for n in range(10)]
        t += [("G", 44.6, 3.5, B, 0.8, True), ("+", 50.7, 17.25, B, 1.0, True), ("-", 50.7, 14.75, B, 1.0, True)]
        return t


class RX:
    name, title = "rx", "ff-expander RX (base)"
    W, H = 54.0, 31.0
    power_nets = ["GND", "+3V3", "+5V", "+5V_XD"]
    # rows top -> bottom follow the XIAO pin order so tracks don't cross:
    # top edge pins D10, D9, D8, D7 (OUT6, 9, 8, 7), bottom edge D5..D0 (OUT5..0)
    ROWS = [6, 9, 8, 7, 5, 4, 3, 2, 1, 0]

    @classmethod
    def row_y(cls, k):
        return cls.H / 2 + 2.75 * (k - 4.5)

    @classmethod
    def placement(cls):
        W, H = cls.W, cls.H
        pl = {"U3": (10.5, H / 2, 90, "F")}  # XIAO: USB-C overhangs the left edge
        # left holes in the corners, right holes just inboard of the connector column
        holes = [(3.5, 3.0), (W - 9.64, 3.0), (3.5, H - 3.0), (W - 9.64, H - 3.0)]
        for n, (x, y) in enumerate(holes):
            pl["H%d" % (n + 1)] = (x, y, 0, "F")
        for k, n in enumerate(cls.ROWS):
            y = cls.row_y(k)
            pl["R%d" % (11 + n)] = (27.0, y, 0, "F")     # 1k:  OUTn | BTNn
            pl["R%d" % (1 + n)] = (31.2, y, 180, "F")    # 10k: BTNn | +3V3
        # shift registers: U2 (buttons 8, 9) on top, U1 below; U2 turned so
        # both VCC pins face the gap where the decoupling caps sit
        pl["U2"] = (37.6, 8.2, 180, "F")
        pl["U1"] = (37.6, 22.8, 0, "F")
        pl["C5"] = (37.6, 14.45, 0, "F")
        pl["C4"] = (37.6, 16.55, 0, "F")
        pl["C3"] = (37.6, 1.5, 0, "F")       # +3V3 bulk
        pl["R21"] = (37.6, 29.6, 0, "F")     # 47R in MISO
        # 5 V input: D1 + caps, next to J2
        pl["D1"] = (44.4, 11.0, 90, "F")
        pl["C1"] = (44.4, 17.4, 90, "F")
        pl["C2"] = (44.4, 21.6, 90, "F")
        # connectors stacked on the right edge
        pl["J1"] = (49.96, 17.5, 90, "F")    # XDRIVE SPI, pin 1 (GND) at the bottom
        pl["J2"] = (49.96, 26.3, 90, "F")    # XDRIVE 5 V
        return pl

    @classmethod
    def texts(cls):
        F, B = pcbnew.F_SilkS, pcbnew.B_SilkS
        t = [("1k", 27.0, 0.9, F, 0.8, False), ("10k", 31.2, 0.9, F, 0.8, False)]
        t += [("B%d" % n, 23.6, cls.row_y(k), F, 0.8, False) for k, n in enumerate(cls.ROWS)]
        t += [("ff-expander RX  rev A", 24.0, 30.0, B, 0.8, True), (NOTICE, 24.0, 1.0, B, 0.8, True)]
        for k, s in enumerate(("GND", "MOSI", "MISO", "SCK", "GPIO6", "3V3")):
            t.append((s, 46.0, 17.5 - 2.5 * k, B, 0.8, True))
        t += [("5V", 46.4, 26.3, B, 0.8, True), ("GND", 46.4, 23.8, B, 0.8, True)]
        return t


BOARDS = {"tx": TX, "rx": RX}


def corners(w, h, ix, iy):
    return [(ix, iy), (w - ix, iy), (ix, h - iy), (w - ix, h - iy)]


# ---- helpers ---------------------------------------------------------------------
def stock_fp_dir():
    for env in ("KICAD10_FOOTPRINT_DIR", "KICAD9_FOOTPRINT_DIR", "KICAD_FOOTPRINT_DIR"):
        if os.environ.get(env):
            return os.environ[env]
    for d in ("/usr/share/kicad/footprints", "/usr/local/share/kicad/footprints"):
        if os.path.isdir(d):
            return d
    cli = shutil.which("kicad-cli")
    if cli:
        m = re.search(r"(/nix/store/[^'\":\s]*kicad-footprints[^'\":\s/]*/share/kicad/footprints)",
                      open(os.path.realpath(cli), errors="ignore").read())
        if m:
            return m.group(1)
        out = subprocess.run(["nix-store", "-qR", os.path.dirname(os.path.dirname(os.path.realpath(cli)))],
                             capture_output=True, text=True).stdout.split()
        for p in out:
            if "kicad-footprints" in p and os.path.isdir(p + "/share/kicad/footprints"):
                return p + "/share/kicad/footprints"
    sys.exit("KiCad footprint libraries not found: set KICAD_FOOTPRINT_DIR")


def paths(spec):
    base = os.path.join(HERE, spec.name, "ff-expander-" + spec.name)
    return base + ".kicad_sch", base + ".kicad_pcb", os.path.join(HERE, spec.name, "drc.rpt")


def read_netlist(sch):
    with tempfile.TemporaryDirectory() as td:
        net = os.path.join(td, "board.net")
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", net, sch],
                       check=True, capture_output=True)
        root = sexpr.parse(open(net).read())
    comps = {}
    for c in sexpr.find(sexpr.find(root, "components")[0], "comp"):
        ref = sexpr.find(c, "ref")[0][1]
        props = {p[1][1]: (p[2][1] if len(p) > 2 else "") for p in sexpr.find(c, "property")}
        comps[ref] = {
            "value": sexpr.find(c, "value")[0][1],
            "footprint": sexpr.find(c, "footprint")[0][1],
            "uuid": sexpr.find(c, "tstamps")[0][1],
            "dnp": "dnp" in props,
        }
    nets = {}
    for n in sexpr.find(sexpr.find(root, "nets")[0], "net"):
        name = sexpr.find(n, "name")[0][1]
        for node in sexpr.find(n, "node"):
            nets[(sexpr.find(node, "ref")[0][1], sexpr.find(node, "pin")[0][1])] = name
    return comps, nets


def setup_rules(board, power_nets):
    ds = board.GetDesignSettings()
    ns = ds.m_NetSettings
    dflt = ns.GetDefaultNetclass()
    dflt.SetClearance(mm(0.2))
    dflt.SetTrackWidth(mm(0.25))
    dflt.SetViaDiameter(mm(0.6))
    dflt.SetViaDrill(mm(0.3))
    pwr = pcbnew.NETCLASS("Power")
    pwr.SetClearance(mm(0.2))
    pwr.SetTrackWidth(mm(0.4))
    pwr.SetViaDiameter(mm(0.7))
    pwr.SetViaDrill(mm(0.35))
    ns.SetNetclass("Power", pwr)
    for n in power_nets:
        ns.SetNetclassPatternAssignment(n, "Power")
    ds.m_MinClearance = mm(0.2)
    ds.m_TrackMinWidth = mm(0.2)
    ds.m_ViasMinSize = mm(0.6)
    ds.m_MinThroughDrill = mm(0.3)
    ds.m_CopperEdgeClearance = mm(0.3)
    ds.m_HoleClearance = mm(0.25)


def add_text(board, s, x, y, layer, size=0.8, mirror=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(P(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    if mirror:
        t.SetMirrored(True)
    board.Add(t)


def add_zone(board, net, layer, w, h):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    ls.AddLayer(layer)
    z.SetLayerSet(ls)
    z.SetNetCode(net.GetNetCode())
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetMinThickness(mm(0.25))
    z.SetThermalReliefGap(mm(0.4))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    z.SetLocalClearance(mm(0.3))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    o = z.Outline()
    o.NewOutline()
    for x, y in [(0, 0), (w, 0), (w, h), (0, h)]:
        o.Append(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))
    board.Add(z)


def add_edge_keepouts(board, w, h, d=0.4):
    """Strips along the outline that forbid tracks/vias, so the autorouter
    respects the copper-to-edge clearance (it doesn't know that rule)."""
    for x0, y0, x1, y1 in [(0, 0, w, d), (0, h - d, w, h), (0, 0, d, h), (w - d, 0, w, h)]:
        z = pcbnew.ZONE(board)
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        ls.AddLayer(pcbnew.B_Cu)
        z.SetLayerSet(ls)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        o = z.Outline()
        o.NewOutline()
        for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            o.Append(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))
        board.Add(z)


# ---- build -----------------------------------------------------------------------
def build(spec, route=True):
    sch, pcb, rpt = paths(spec)
    comps, pins = read_netlist(sch)
    fpdir = stock_fp_dir()
    board = pcbnew.NewBoard(pcb)
    setup_rules(board, spec.power_nets)
    tb = board.GetTitleBlock()
    tb.SetTitle(spec.title)
    tb.SetRevision("A")
    tb.SetDate("2026-11-23")
    tb.SetComment(0, COPYRIGHT)

    nets = {}
    for name in sorted(set(pins.values())):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni

    pl = spec.placement()
    missing = set(comps) - set(pl)
    if missing:
        sys.exit("%s: no placement for %s" % (spec.name, sorted(missing)))
    for ref, c in sorted(comps.items()):
        nick, name = c["footprint"].split(":")
        fp = pcbnew.FootprintLoad(OWN_FP.get(nick, os.path.join(fpdir, nick + ".pretty")), name)
        if fp is None:
            sys.exit("footprint not found: " + c["footprint"])
        fp.SetFPID(pcbnew.LIB_ID(nick, name))
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + c["uuid"]))
        fp.SetSheetname("/")
        fp.SetSheetfile(os.path.basename(sch))
        x, y, rot, side = pl[ref]
        board.Add(fp)
        fp.SetPosition(P(x, y))
        fp.SetOrientationDegrees(rot)
        if side == "B":
            fp.Flip(P(x, y), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
        if c["dnp"]:
            fp.SetDNP(True)
        for pad in fp.Pads():
            net = pins.get((ref, pad.GetNumber()))
            if net:
                pad.SetNet(nets[net])
        if ref[0] in "RCDHJ":
            # dense rows: designators live on the fab layer, the silkscreen
            # gets column / pin labels instead
            fp.Reference().SetLayer(pcbnew.B_Fab if side == "B" else pcbnew.F_Fab)
        else:
            fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
            fp.Reference().SetTextThickness(mm(0.12))
            if name.startswith("SOIC"):
                # inside the outline, between the pad rows
                fp.Reference().SetPosition(P(x, y))
                fp.Reference().SetTextAngleDegrees(90)

    r = pcbnew.PCB_SHAPE(board)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetStart(P(0, 0))
    r.SetEnd(P(spec.W, spec.H))
    r.SetLayer(pcbnew.Edge_Cuts)
    r.SetWidth(mm(0.1))
    board.Add(r)
    for s, x, y, layer, size, mirror in spec.texts():
        add_text(board, s, x, y, layer, size, mirror)

    add_edge_keepouts(board, spec.W, spec.H)
    board.BuildConnectivity()
    if route:
        autoroute(board, spec.name)
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        add_zone(board, nets["GND"], layer, spec.W, spec.H)
    pcbnew.SaveBoard(pcb, board)
    # final zone fill + DRC by KiCad itself (the in-process fill can be stale)
    subprocess.run(["kicad-cli", "pcb", "drc", "--refill-zones", "--save-board", "--severity-all",
                    "-o", rpt, pcb], capture_output=True)
    print("wrote", pcb, "- DRC report:", rpt)


def autoroute(board, name):
    exe = shutil.which("freerouting")
    if not exe:
        sys.exit("freerouting not on PATH (nix shell nixpkgs#freerouting)")
    with tempfile.TemporaryDirectory() as td:
        dsn, ses = os.path.join(td, name + ".dsn"), os.path.join(td, name + ".ses")
        if not pcbnew.ExportSpecctraDSN(board, dsn):
            sys.exit("DSN export failed")
        env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        env["JAVA_TOOL_OPTIONS"] = "-Djava.awt.headless=true"
        cmd = [exe, "-de", dsn, "-do", ses, "-mp", "200", "--gui.enabled=false"]
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900)
        if not os.path.exists(ses):
            print(res.stdout[-3000:], res.stderr[-3000:])
            sys.exit("freerouting produced no session file")
        if not pcbnew.ImportSpecctraSES(board, ses):
            sys.exit("SES import failed")


def unrouted(spec):
    return open(paths(spec)[2]).read().count("[unconnected_items]")


def main():
    route = "--no-route" not in sys.argv
    names = [a for a in sys.argv[1:] if not a.startswith("-")] or list(BOARDS)
    for name in names:
        spec = BOARDS[name]
        for attempt in range(1, 6):
            build(spec, route=route)
            if not route or not unrouted(spec):
                break
            print("%s: attempt %d left %d connection(s) unrouted, retrying" % (name, attempt, unrouted(spec)))
        else:
            sys.exit("%s: could not route every connection" % name)


if __name__ == "__main__":
    main()
