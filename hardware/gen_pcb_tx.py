#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate the TX (wheel) PCB: tx/ff-expander-tx.kicad_pcb.

Reads the netlist from the TX schematic, places every footprint, draws the
52 x 32 mm outline, autoroutes with Freerouting, pours GND on both layers and
leaves the board ready for DRC.

Run (needs KiCad's pcbnew module and freerouting on PATH):
    nix shell nixpkgs#kicad-small nixpkgs#freerouting -c ./kicad-python.sh gen_pcb_tx.py
Options: --no-route  place only (keep ratsnest, no tracks)
"""
import glob
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
SCH = os.path.join(HERE, "tx", "ff-expander-tx.kicad_sch")
PCB = os.path.join(HERE, "tx", "ff-expander-tx.kicad_pcb")
OWN_FP = {"ff-expander": os.path.join(HERE, "lib", "ff-expander.pretty")}

BOARD_W, BOARD_H = 52.0, 32.0
HOLE_INSET = 3.5           # 45 x 25 mm hole pattern
ORIGIN = (100.0, 80.0)     # where the board sits on the KiCad page
POWER_NETS = ["GND", "+3V3", "VBAT"]
NOTICE = "CERN-OHL-S-2.0  github.com/LongerHV/ff-expander"

mm = pcbnew.FromMM


def P(x, y):
    return pcbnew.VECTOR2I(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))


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


def read_netlist():
    with tempfile.TemporaryDirectory() as td:
        net = os.path.join(td, "tx.net")
        subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", net, SCH],
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


# ---- placement ---------------------------------------------------------------
# (x, y, rotation, side) in board mm; side "B" = bottom.
def placement():
    pl = {"U1": (10.5, 16.0, 90, "F")}   # XIAO: USB-C overhangs the left edge
    i = HOLE_INSET
    for n, (x, y) in enumerate([(i, i), (BOARD_W - i, i), (i, BOARD_H - i), (BOARD_W - i, BOARD_H - i)]):
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


def setup_rules(board):
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
    for n in POWER_NETS:
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


def add_zone(board, net, layer):
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
    for x, y in [(0, 0), (BOARD_W, 0), (BOARD_W, BOARD_H), (0, BOARD_H)]:
        o.Append(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))
    board.Add(z)


def build(route=True):
    comps, pins = read_netlist()
    fpdir = stock_fp_dir()
    board = pcbnew.NewBoard(PCB)
    setup_rules(board)
    tb = board.GetTitleBlock()
    tb.SetTitle("ff-expander TX (wheel)")
    tb.SetRevision("A")
    tb.SetDate("2026-11-23")
    tb.SetComment(0, "(c) 2026 Michal Mieszczak. CERN-OHL-S-2.0. Source: https://github.com/LongerHV/ff-expander")

    nets = {}
    for name in sorted(set(pins.values())):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni

    pl = placement()
    missing = set(comps) - set(pl)
    if missing:
        sys.exit("no placement for: %s" % sorted(missing))
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
        fp.SetSheetfile(os.path.basename(SCH))
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
        if ref[0] in "RCHJ":
            # rows are too tight for designators: keep them on the fab layer,
            # the silkscreen gets column labels instead
            fp.Reference().SetLayer(pcbnew.B_Fab if side == "B" else pcbnew.F_Fab)
        else:
            fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
            fp.Reference().SetTextThickness(mm(0.12))

    # outline
    r = pcbnew.PCB_SHAPE(board)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetStart(P(0, 0))
    r.SetEnd(P(BOARD_W, BOARD_H))
    r.SetLayer(pcbnew.Edge_Cuts)
    r.SetWidth(mm(0.1))
    board.Add(r)

    # silkscreen
    for x, s in ((26.95, "10k"), (31.15, "10n"), (35.35, "1k")):
        add_text(board, s, x, 1.3, pcbnew.F_SilkS, 0.8)
    for n in range(10):
        add_text(board, "B%d" % n, 23.6, 3.6 + 2.75 * (9 - n), pcbnew.F_SilkS, 0.8)
    add_text(board, "ff-expander TX  rev A", 31.0, 30.9, pcbnew.B_SilkS, 0.8, mirror=True)
    add_text(board, NOTICE, 24.0, 1.2, pcbnew.B_SilkS, 0.8, mirror=True)
    for n in range(10):
        add_text(board, "%d" % n, 44.6, 28.5 - 2.5 * n, pcbnew.B_SilkS, 0.8, mirror=True)
    add_text(board, "G", 44.6, 3.5, pcbnew.B_SilkS, 0.8, mirror=True)
    for k, line in enumerate(("XIAO BAT +/-: wire first,", "thread wires through slot,",
                              "solder XIAO, then wires", "to the +/- pads here.")):
        add_text(board, line, 31.8, 7.0 + 1.3 * k, pcbnew.B_SilkS, 0.8, mirror=True)
    add_text(board, "+", 50.7, 17.25, pcbnew.B_SilkS, 1.0, mirror=True)
    add_text(board, "-", 50.7, 14.75, pcbnew.B_SilkS, 1.0, mirror=True)

    board.BuildConnectivity()
    if route:
        autoroute(board)
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        add_zone(board, nets["GND"], layer)
    pcbnew.SaveBoard(PCB, board)
    # final zone fill + DRC by KiCad itself (the in-process fill can be stale)
    rpt = os.path.join(HERE, "tx", "drc.rpt")
    subprocess.run(["kicad-cli", "pcb", "drc", "--refill-zones", "--save-board", "--severity-all",
                    "-o", rpt, PCB], capture_output=True)
    print("wrote", PCB, "- DRC report:", rpt)


def autoroute(board):
    exe = shutil.which("freerouting")
    if not exe:
        sys.exit("freerouting not on PATH (nix shell nixpkgs#freerouting)")
    with tempfile.TemporaryDirectory() as td:
        dsn, ses = os.path.join(td, "tx.dsn"), os.path.join(td, "tx.ses")
        if not pcbnew.ExportSpecctraDSN(board, dsn):
            sys.exit("DSN export failed")
        env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        env["JAVA_TOOL_OPTIONS"] = "-Djava.awt.headless=true"
        cmd = [exe, "-de", dsn, "-do", ses, "-mp", "200", "--gui.enabled=false"]
        print("routing:", " ".join(cmd))
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=900)
        if not os.path.exists(ses):
            print(res.stdout[-3000:], res.stderr[-3000:])
            sys.exit("freerouting produced no session file")
        if not pcbnew.ImportSpecctraSES(board, ses):
            sys.exit("SES import failed")


def unrouted():
    rpt = open(os.path.join(HERE, "tx", "drc.rpt")).read()
    return rpt.count("[unconnected_items]")


if __name__ == "__main__":
    route = "--no-route" not in sys.argv
    for attempt in range(1, 6):
        build(route=route)
        if not route or not unrouted():
            break
        print("attempt %d left %d connection(s) unrouted, retrying" % (attempt, unrouted()))
    else:
        sys.exit("could not route every connection")
