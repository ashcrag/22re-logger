#!/usr/bin/env python3
"""22re-logger laptop side.

  python3 pc/logger.py demo                     synthetic run, no hardware
  python3 pc/logger.py ports                    list serial ports
  python3 pc/logger.py probe --port PORT        1 s snapshot of every input
  python3 pc/logger.py log --port PORT          stream to logs/*.csv (Ctrl-C to stop)
  python3 pc/logger.py log --port PORT --sim 800   bench test with the simulator
  python3 pc/logger.py calibrate --port PORT --light 5

While logging, type a word and press Enter (or just Enter) to drop a
numbered marker into the CSV, e.g. "rev", "release", "stumble".
"""

import argparse
import csv
import datetime as dt
import os
import statistics
import sys
import threading
import time

import config
import decode
import demo

LOG_DIR = os.path.join(decode.REPO_ROOT, "logs")


def open_port(port):
    try:
        import serial
    except ImportError:
        sys.exit("pyserial is missing: pip install -r pc/requirements.txt")
    ser = serial.Serial(port, 115200, timeout=0.5)
    time.sleep(2.0)  # opening the port resets the Nano
    ser.reset_input_buffer()
    ser.write(b"ID\n")
    deadline = time.time() + 3
    while time.time() < deadline:
        line = ser.readline().decode(errors="replace").strip()
        if line.startswith("22RE-LOGGER"):
            print("bridge:", line)
            return ser
    ser.close()
    sys.exit("No 22RE-LOGGER answered on %s. Wrong port, or firmware not flashed?" % port)


def send(ser, cmd):
    ser.write((cmd + "\n").encode())


def new_log_path(prefix):
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return os.path.join(LOG_DIR, "%s_%s.csv" % (prefix, stamp))


def status_line(row):
    tm = row["timing_btdc"]
    tm = "%5.1f" % tm if tm != "" else "  n/a"
    inj = row["inj_ms"]
    inj = "%5.2f" % inj if inj != "" else "  n/a"
    return "t=%7.1fs rpm=%5d timing=%s inj=%sms ox=%.2f vs=%.2f idl=%s batt=%.1f" % (
        row["t_s"], row["rpm"], tm, inj, row["ox"], row["vs"],
        "closed" if row["idl_closed"] else "open  ", row["batt"])


class Marker:
    """Reads stdin lines in the background; each one becomes a marker."""

    def __init__(self):
        self.count = 0
        self.pending = []
        self.lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        for line in sys.stdin:
            with self.lock:
                self.count += 1
                self.pending.append((self.count, line.strip()))

    def take(self):
        with self.lock:
            out, self.pending = self.pending, []
        return out


def write_rows(path, rows_iter, live=True):
    marker = Marker() if live and sys.stdin.isatty() else None
    n = 0
    last_print = 0.0
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=decode.CSV_FIELDS)
        w.writeheader()
        try:
            for row in rows_iter:
                if marker:
                    for num, text in marker.take():
                        row["mark"], row["note"] = num, text
                        print("\n  marker %d %s at t=%.1fs" % (num, text, row["t_s"]))
                w.writerow(row)
                n += 1
                if live and time.time() - last_print > 0.25:
                    print("\r" + status_line(row), end="", flush=True)
                    last_print = time.time()
        except KeyboardInterrupt:
            pass
    print("\nwrote %d rows to %s" % (n, os.path.relpath(path)))


def cmd_demo(args):
    path = new_log_path("demo")
    raw_lines = (
        "D," + ",".join(str(r[k]) for k in decode.RAW_FIELDS) for r in demo.frames(args.seconds)
    )

    def rows():
        for line in raw_lines:
            raw = decode.parse(line)
            if raw is None:
                sys.exit("demo frame failed to parse: %s" % line)
            yield decode.convert(raw, demo.DEMO_CAL)

    write_rows(path, rows(), live=False)
    print("synthetic data, not a real engine. Next: python3 pc/summarize.py %s" % os.path.relpath(path))


def cmd_ports(_args):
    try:
        from serial.tools import list_ports
    except ImportError:
        sys.exit("pyserial is missing: pip install -r pc/requirements.txt")
    ports = list(list_ports.comports())
    if not ports:
        print("no serial ports found")
    for p in ports:
        print("%-28s %s" % (p.device, p.description))


def cmd_probe(args):
    ser = open_port(args.port)
    if args.sim:
        send(ser, "SIM %d" % args.sim)
        time.sleep(0.3)
    send(ser, "PROBE")
    deadline = time.time() + 4
    print("%-4s %-34s %8s %8s %8s   (signal volts, divider applied)" % ("pin", "signal", "min", "max", "avg"))
    while time.time() < deadline:
        line = ser.readline().decode(errors="replace").strip()
        if not line.startswith("P,"):
            continue
        parts = line.split(",")
        if parts[1] == "END":
            break
        if parts[1].startswith("A"):
            idx = int(parts[1][1:])
            key, label, divider = config.CHANNELS[idx]
            mn, mx, avg = (decode.counts_to_volts(int(x), divider) for x in parts[2:5])
            flag = "  near top of range, check divider" if int(parts[3]) >= 1015 else ""
            print("%-4s %-34s %8.3f %8.3f %8.3f%s" % (parts[1], label, mn, mx, avg, flag))
        else:
            names = {"D2": "crank pickup", "D3": "IGT", "D4": "injector"}
            print("%-4s %-34s edges/s=%-6s level=%s" % (parts[1], names.get(parts[1], ""), parts[2], parts[3]))
    if args.sim:
        send(ser, "SIM 0")
    ser.close()


def serial_rows(ser, cal, seconds=None):
    t0 = None
    start = time.time()
    while seconds is None or time.time() - start < seconds:
        line = ser.readline().decode(errors="replace")
        raw = decode.parse(line)
        if raw is None:
            continue
        if t0 is None:
            t0 = raw["ms"]
        yield decode.convert(raw, cal, t0)


def cmd_log(args):
    cal = decode.load_calibration()
    if not cal:
        print("no calibration.json yet: timing_btdc stays blank (spark_angle_raw is still logged)")
    ser = open_port(args.port)
    send(ser, "RATE %d" % args.rate)
    if args.sim:
        send(ser, "SIM %d" % args.sim)
    send(ser, "GO")
    prefix = "sim" if args.sim else "run"
    if args.name:
        prefix += "_" + args.name.replace(" ", "-")
    path = new_log_path(prefix)
    print("logging to %s. Type a word + Enter to drop a marker. Ctrl-C stops." % os.path.relpath(path))
    try:
        write_rows(path, serial_rows(ser, cal, args.seconds))
    finally:
        send(ser, "STOP")
        if args.sim:
            send(ser, "SIM 0")
        ser.close()


def cmd_calibrate(args):
    """Engine idling with T-E1 jumped (fixed base timing) and a timing light reading."""
    ser = open_port(args.port)
    send(ser, "RATE 50")
    send(ser, "GO")
    print("sampling 5 s at idle...")
    raws = []
    t_end = time.time() + 5
    while time.time() < t_end:
        raw = decode.parse(ser.readline().decode(errors="replace"))
        if raw:
            raws.append(raw)
    send(ser, "STOP")
    ser.close()
    best = None
    for edge in ("fall", "rise"):
        angles = [a for a in (decode.spark_angle(r, edge) for r in raws) if a is not None]
        if len(angles) < 20:
            continue
        # angles live on a 180 deg circle; measure around the first one so a wrap doesn't split them
        ref = angles[0]
        rel = [((a - ref + 90.0) % 180.0) - 90.0 for a in angles]
        spread = statistics.pstdev(rel)
        med = (ref + statistics.median(rel)) % 180.0
        print("  %s edge: %d samples, median %.2f deg after pickup, spread %.2f deg" % (edge, len(angles), med, spread))
        if best is None or spread < best[2]:
            best = (edge, med, spread)
    if best is None:
        sys.exit("No usable crank + IGT data. Check the crank pickup and IGT tap with probe.")
    edge, med, spread = best
    offset = (args.light + med) % 180.0
    cal = {
        "offset_deg": round(offset, 2),
        "edge": edge,
        "light_reading_btdc": args.light,
        "spread_deg": round(spread, 2),
        "date": dt.date.today().isoformat(),
    }
    path = decode.save_calibration(cal)
    print("using %s edge (steadier). offset %.2f deg saved to %s" % (edge, offset, os.path.relpath(path)))
    if spread > 1.5:
        print("warning: spread over 1.5 deg. Idle may be unsteady or the pickup is noisy; recheck before trusting timing.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("demo", help="synthetic run, no hardware")
    p.add_argument("--seconds", type=float, default=45.0)
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("ports", help="list serial ports")
    p.set_defaults(func=cmd_ports)

    p = sub.add_parser("probe", help="1 s snapshot of every input")
    p.add_argument("--port", required=True)
    p.add_argument("--sim", type=int, default=0, help="bench only: run the simulator at this rpm")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("log", help="stream frames to logs/*.csv")
    p.add_argument("--port", required=True)
    p.add_argument("--rate", type=int, default=50, help="frames per second (1-100)")
    p.add_argument("--sim", type=int, default=0, help="bench only: run the simulator at this rpm")
    p.add_argument("--seconds", type=float, default=None, help="stop after this long")
    p.add_argument("--name", default="", help="short tag for the file name, e.g. warm-idle")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("calibrate", help="set crank pickup offset from a timing light reading")
    p.add_argument("--port", required=True)
    p.add_argument("--light", type=float, required=True, help="timing light reading, degrees BTDC")
    p.set_defaults(func=cmd_calibrate)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
