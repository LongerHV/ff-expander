#!/usr/bin/env python3
"""End-to-end link test for ff-expander, no buttons or shift registers needed.

Drives the TX board's simulated-button console and watches the RX board's
output log over USB. Checks every button arrives, measures host-observed
latency, verifies the failsafe (mute + TX reboot) releases all buttons, and
reports packet loss.

    python3 tools/link_test.py [--tx PORT] [--rx PORT]
"""

import argparse
import queue
import re
import statistics
import sys
import threading
import time

import serial

BY_ID = "/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_10:BD:A3:B1:B9:{}-if00"
NUM_BUTTONS = 10
ALL = (1 << NUM_BUTTONS) - 1

RX_LINE = re.compile(r"^RX t=\d+ btn=0x([0-9a-f]+) seq=\d+ link=(up|down)")
STAT_LINE = re.compile(r"^STAT link=(\w+) btn=0x[0-9a-f]+ received=(\d+) lost=(\d+) stale=(\d+)")


class Board:
    """Serial port with a reader thread; survives the device re-enumerating."""

    def __init__(self, name, port):
        self.name, self.port = name, port
        self.lines = queue.Queue()
        self.ser = None
        self._open()
        threading.Thread(target=self._reader, daemon=True).start()

    def _open(self, timeout=10.0):
        deadline = time.monotonic() + timeout
        while True:
            try:
                # Leave DTR/RTS alone: toggling them resets the ESP32-C6.
                ser = serial.Serial()
                ser.port, ser.baudrate, ser.timeout = self.port, 115200, 0.05
                ser.dtr = ser.rts = False
                ser.open()
                self.ser = ser
                return
            except serial.SerialException:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)

    def _reader(self):
        buf = b""
        while True:
            try:
                # read(1) returns on the first byte; then take whatever else is buffered
                chunk = self.ser.read(1)
                if chunk and self.ser.in_waiting:
                    chunk += self.ser.read(self.ser.in_waiting)
            except (serial.SerialException, OSError):
                time.sleep(0.2)
                try:
                    self._open()
                except serial.SerialException:
                    pass
                continue
            if not chunk:
                continue
            now = time.perf_counter()
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self.lines.put((now, line.decode(errors="replace").strip()))

    def send(self, cmd):
        t = time.perf_counter()
        self.ser.write((cmd + "\n").encode())
        self.ser.flush()
        return t

    def drain(self):
        while not self.lines.empty():
            self.lines.get_nowait()

    def wait_for(self, pattern, timeout=1.0):
        """Return (host_time, match) for the first line matching pattern."""
        deadline = time.perf_counter() + timeout
        while True:
            left = deadline - time.perf_counter()
            if left <= 0:
                return None, None
            try:
                t, line = self.lines.get(timeout=left)
            except queue.Empty:
                return None, None
            m = pattern(line) if callable(pattern) else re.search(pattern, line)
            if m:
                return t, m


def rx_state(btn=None, link=None):
    def match(line):
        m = RX_LINE.match(line)
        if not m:
            return None
        if btn is not None and int(m.group(1), 16) != btn:
            return None
        if link is not None and m.group(2) != link:
            return None
        return m

    return match


def rx_stats(rx):
    rx.drain()
    rx.send("s")
    _, m = rx.wait_for(STAT_LINE.match, 1.0)
    if not m:
        raise RuntimeError("no STAT from RX")
    return {"link": m.group(1), "received": int(m.group(2)), "lost": int(m.group(3)), "stale": int(m.group(4))}


class Results:
    def __init__(self):
        self.failures = []

    def check(self, ok, what):
        print(f"  [{'PASS' if ok else 'FAIL'}] {what}")
        if not ok:
            self.failures.append(what)


def set_mask(tx, rx, mask, timeout=0.5):
    """Set simulated buttons on TX; return host latency until RX shows it, or None."""
    rx.drain()
    t0 = tx.send(f"m 0x{mask:x}")
    t1, _ = rx.wait_for(rx_state(btn=mask), timeout)
    return None if t1 is None else (t1 - t0) * 1000


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tx", default=BY_ID.format("84"))
    ap.add_argument("--rx", default=BY_ID.format("00"))
    ap.add_argument("--soak", type=float, default=10.0, help="seconds of heartbeat-only soak")
    args = ap.parse_args()

    tx, rx = Board("tx", args.tx), Board("rx", args.rx)
    r = Results()

    print("== link up")
    tx.send("m 0")
    deadline = time.monotonic() + 5
    while rx_stats(rx)["link"] != "up" and time.monotonic() < deadline:
        time.sleep(0.2)
    r.check(rx_stats(rx)["link"] == "up", "RX reports link up")
    time.sleep(0.1)

    print("== host serial overhead (RX console round trip)")
    rtts = []
    for _ in range(20):
        rx.drain()
        t0 = rx.send("s")
        t1, _ = rx.wait_for(STAT_LINE.match, 1.0)
        if t1:
            rtts.append((t1 - t0) * 1000)
    print(f"  USB command->reply round trip: median {statistics.median(rtts):.2f} ms")

    print("== every button, press and release")
    lat = []
    for b in range(NUM_BUTTONS):
        down = set_mask(tx, rx, 1 << b)
        up = set_mask(tx, rx, 0)
        r.check(down is not None and up is not None, f"button {b} press/release reaches RX")
        lat += [x for x in (down, up) if x is not None]

    print("== patterns")
    for mask in (ALL, 0x155, 0x2AA, 0x000):
        x = set_mask(tx, rx, mask)
        r.check(x is not None, f"mask 0x{mask:03x} reaches RX")
        if x is not None:
            lat.append(x)

    print("== latency (host: TX command written -> RX log line read)")
    lat.sort()
    print(
        f"  n={len(lat)} min {lat[0]:.2f}  median {statistics.median(lat):.2f}  "
        f"p95 {lat[int(len(lat) * 0.95) - 1]:.2f}  max {lat[-1]:.2f} ms"
    )
    print("  (includes two USB hops; see round trip above)")

    print("== rapid changes (200 masks, 5 ms apart)")
    before = rx_stats(rx)
    rx.drain()
    for i in range(200):
        tx.send(f"m 0x{(i * 37) & ALL:x}")
        time.sleep(0.005)
    final = (199 * 37) & ALL
    t, _ = rx.wait_for(rx_state(btn=final), 1.0)
    r.check(t is not None, f"RX settles on final mask 0x{final:03x}")
    after = rx_stats(rx)
    print(
        f"  received {after['received'] - before['received']}, lost {after['lost'] - before['lost']}, "
        f"stale {after['stale'] - before['stale']}"
    )
    set_mask(tx, rx, 0)

    print("== failsafe: TX goes silent while buttons held")
    set_mask(tx, rx, ALL)
    rx.drain()
    t0 = tx.send("mute 400")
    t1, _ = rx.wait_for(rx_state(btn=0, link="down"), 1.0)
    r.check(t1 is not None, "RX releases all buttons when link is lost")
    if t1:
        print(f"  released {(t1 - t0) * 1000:.0f} ms after mute (timeout is 100 ms)")
    t2, _ = rx.wait_for(rx_state(btn=ALL, link="up"), 1.0)
    r.check(t2 is not None, "RX restores held buttons when link returns")

    print("== failsafe: TX reboots while buttons held")
    set_mask(tx, rx, 0x003)
    rx.drain()
    tx.send("reboot")
    t1, _ = rx.wait_for(rx_state(btn=0, link="down"), 1.0)
    r.check(t1 is not None, "RX releases buttons when TX resets")
    t2, _ = rx.wait_for(rx_state(btn=0, link="up"), 5.0)
    r.check(t2 is not None, "link comes back after TX reboot")
    time.sleep(0.5)
    r.check(set_mask(tx, rx, 0x200, timeout=2.0) is not None, "TX works after reboot")
    set_mask(tx, rx, 0)

    print(f"== soak: {args.soak:.0f} s of heartbeats")
    before = rx_stats(rx)
    time.sleep(args.soak)
    after = rx_stats(rx)
    got = after["received"] - before["received"]
    lost = after["lost"] - before["lost"]
    rate = got / args.soak
    print(f"  {rate:.1f} packets/s, lost {lost} ({100 * lost / max(1, got + lost):.2f} %)")
    r.check(rate > 40, "heartbeat rate ~50/s")
    r.check(after["link"] == "up", "link stayed up")

    print()
    if r.failures:
        print(f"FAILED: {len(r.failures)} check(s)")
        for f in r.failures:
            print(f"  - {f}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
