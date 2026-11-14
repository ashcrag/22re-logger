#!/usr/bin/env python3
"""toyota-tap-logger laptop side. Every command takes --engine (22re or 1uz).

  python3 pc/logger.py demo --engine 1uz                synthetic run, no hardware
  python3 pc/logger.py ports                            list serial ports
  python3 pc/logger.py probe --engine 1uz --port PORT   1 s snapshot of every input
  python3 pc/logger.py ecu --port PORT                  1UZ: watch the VF1 stream (TE2-E1 jumped)
  python3 pc/logger.py log --engine 1uz --port PORT     stream to logs/*.csv (Ctrl-C to stop)
  python3 pc/logger.py log --engine 1uz --port PORT --sim 800   bench test with the simulator
  python3 pc/logger.py calibrate --engine 1uz --port PORT --light 10

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

import decode
import profiles
import vf1

LOG_DIR = os.path.join(decode.REPO_ROOT, "logs")
BANNER = "TAP-LOGGER"


# ---------- frame stream -> rows ----------

class Stream:
    """Turns firmware lines (H, D, E) into CSV rows for one engine profile."""

    def __init__(self, prof, cal, vf1_invert=False):
        self.prof = prof
        self.cal = cal
        self.fields = list(prof.RAW_FIELDS)
        self.t0 = None
        self.last_t = 0.0
        self.decoder = vf1.VF1Decoder(invert=vf1_invert) if prof.HAS_VF1 else None
        self.ecu = None
        self.ecu_t = None
        self.new_ecu = []

    def feed(self, line):
        hdr = decode.parse_header(line)
        if hdr:
            self.fields = hdr
            return None
        if self.decoder is not None:
            edge = decode.parse_edge(line)
            if edge:
                frame = self.decoder.edge(*edge)
                if frame:
                    self.ecu = vf1.interpret(*frame)
                    self.ecu_t = None  # stamped on the next row, which then has age 0
                    self.new_ecu.append(self.ecu)
                return None
        raw = decode.parse(line, self.fields)
        if raw is None:
            return None
        if self.t0 is None:
            self.t0 = raw["ms"]
        row = self.prof.convert(raw, self.cal, self.t0)
        self.last_t = row["t_s"]
        if self.ecu:
            if self.ecu_t is None:
                self.ecu_t = row["t_s"]
            row.update(self.ecu)
            row["ecu_age_s"] = round(row["t_s"] - self.ecu_t, 2)
        return row

    def fieldnames(self):
        return decode.COMMON_FIELDS + self.prof.EXTRA_FIELDS


# ---------- serial ----------

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
        if BANNER in line:
            print("bridge:", line)
            return ser, line
    ser.close()
    sys.exit("No logger answered on %s. Wrong port, or firmware not flashed?" % port)


def check_firmware(banner, prof):
    want = {"22re": "22RE", "1uz": "1UZ"}[prof.NAME]
    if want not in banner:
        sys.exit("This Nano runs '%s' but --engine is %s. Flash %s." % (banner, prof.NAME, prof.SKETCH))


def send(ser, cmd):
    ser.write((cmd + "\n").encode())


def serial_lines(ser, seconds=None):
    start = time.time()
    while seconds is None or time.time() - start < seconds:
        yield ser.readline().decode(errors="replace")


# ---------- output ----------

def new_log_path(prefix):
    os.makedirs(LOG_DIR, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return os.path.join(LOG_DIR, "%s_%s.csv" % (prefix, stamp))


def fmt(v, spec):
    return spec % v if v not in ("", None) else "n/a".rjust(len(spec % 0))


def status_line(row):
    return "t=%7.1fs rpm=%5d timing=%s inj=%sms air=%s ox=%.2f idl=%s batt=%.1f" % (
        row["t_s"], row["rpm"], fmt(row["timing_btdc"], "%5.1f"), fmt(row["inj_ms"], "%5.2f"),
        fmt(row["airflow"], "%6.1f"), row["ox"], "closed" if row["idl_closed"] else "open  ", row["batt"])


def ecu_line(e):
    flags = [name for name in ("closed_loop", "idle", "neutral", "ac", "starter", "knock", "cold")
             if e.get("ecu_" + name) == 1]
    return "ECU frame id=%s n=%s rpm=%s timing=%s inj=%sms ect=%sC tps=%s%% iac=%s%% flags=[%s]  raw: %s" % (
        e["ecu_id"], e["ecu_n"], e["ecu_rpm"], e["ecu_timing"], e["ecu_inj_ms"], e["ecu_ect_c"],
        e["ecu_tps_pct"], e["ecu_iac_pct"], " ".join(flags), e["ecu_raw"])


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


def write_rows(path, stream, lines, live=True):
    marker = Marker() if live and sys.stdin.isatty() else None
    n = 0
    last_print = 0.0
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=stream.fieldnames(), extrasaction="ignore")
        w.writeheader()
        try:
            for line in lines:
                row = stream.feed(line)
                if live:
                    for e in stream.new_ecu:
                        print("\n  " + ecu_line(e))
                stream.new_ecu.clear()
                if row is None:
                    continue
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
    if stream.decoder is not None:
        print("VF1 frames decoded: %d, framing errors: %d" % (stream.decoder.frames, stream.decoder.fails))


# ---------- commands ----------

def cmd_demo(args):
    prof = profiles.get(args.engine)
    path = new_log_path("demo_" + prof.NAME)
    stream = Stream(prof, prof.DEMO_CAL)
    write_rows(path, stream, prof.demo_lines(args.seconds), live=False)
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
    prof = profiles.get(args.engine)
    ser, banner = open_port(args.port)
    check_firmware(banner, prof)
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
            key, label, divider = prof.CHANNELS[int(parts[1][1:])]
            mn, mx, avg = (decode.counts_to_volts(int(x), divider) for x in parts[2:5])
            flag = "  near top of range, check divider" if int(parts[3]) >= 1015 else ""
            print("%-4s %-34s %8.3f %8.3f %8.3f%s" % (parts[1], label, mn, mx, avg, flag))
        else:
            print("%-4s %-34s edges/s=%-6s level=%s" % (parts[1], prof.PROBE_NAMES.get(parts[1], ""), parts[2], parts[3]))
    if args.sim:
        send(ser, "SIM 0")
    ser.close()


def cmd_ecu(args):
    prof = profiles.get("1uz")
    ser, banner = open_port(args.port)
    check_firmware(banner, prof)
    stream = Stream(prof, None, vf1_invert=args.invert)
    send(ser, "RATE 5")
    send(ser, "GO")
    print("Watching VF1 for %d s (TE2 must be jumped to E1, key on). A frame takes about 1.5 s." % args.seconds)
    edges = 0
    try:
        for line in serial_lines(ser, args.seconds):
            if line.startswith("E,"):
                edges += 1
            stream.feed(line)
            for e in stream.new_ecu:
                print(ecu_line(e))
            stream.new_ecu.clear()
    except KeyboardInterrupt:
        pass
    send(ser, "STOP")
    ser.close()
    d = stream.decoder
    print("edges seen %d, frames %d, framing errors %d" % (edges, d.frames, d.fails))
    if edges == 0:
        print("No activity on VF1: check TE2-E1 jumper, key on, the VF1 tap, and the comparator (probe D8).")
    elif d.frames == 0:
        print("Edges but no frames: try --invert, or the stream isn't the expected format.")


def cmd_log(args):
    prof = profiles.get(args.engine)
    cal = decode.load_calibration(prof.NAME)
    if not cal:
        print("no calibration_%s.json yet: timing_btdc stays blank (spark_angle_raw is still logged)" % prof.NAME)
    ser, banner = open_port(args.port)
    check_firmware(banner, prof)
    send(ser, "RATE %d" % args.rate)
    if args.sim:
        send(ser, "SIM %d" % args.sim)
    send(ser, "GO")
    prefix = ("sim_" if args.sim else "run_") + prof.NAME
    if args.name:
        prefix += "_" + args.name.replace(" ", "-")
    path = new_log_path(prefix)
    print("logging to %s. Type a word + Enter to drop a marker. Ctrl-C stops." % os.path.relpath(path))
    try:
        write_rows(path, Stream(prof, cal, args.invert), serial_lines(ser, args.seconds))
    finally:
        send(ser, "STOP")
        if args.sim:
            send(ser, "SIM 0")
        ser.close()


def cmd_calibrate(args):
    """Engine idling at fixed base timing (diag jumper in) with a timing light reading."""
    prof = profiles.get(args.engine)
    ser, banner = open_port(args.port)
    check_firmware(banner, prof)
    send(ser, "RATE 50")
    send(ser, "GO")
    print("sampling 5 s at idle (%s)..." % prof.BASE_TIMING_NOTE)
    stream = Stream(prof, None)
    raws = []
    t_end = time.time() + 5
    while time.time() < t_end:
        line = ser.readline().decode(errors="replace")
        stream.feed(line)  # keeps header/fields current
        raw = decode.parse(line, stream.fields)
        if raw:
            raws.append(raw)
    send(ser, "STOP")
    ser.close()
    edges = ("fall", "rise") if prof.NAME == "22re" else ("fall",)
    best = None
    for edge in edges:
        angles = [a for a in (prof.spark_angle(r, edge) for r in raws) if a is not None]
        if len(angles) < 20:
            continue
        ref = angles[0]  # measure around one sample so the fold doesn't split them
        rel = [((a - ref + 90.0) % 180.0) - 90.0 for a in angles]
        spread = statistics.pstdev(rel)
        med = (ref + statistics.median(rel)) % prof.ANGLE_SPAN
        print("  %s edge: %d samples, median %.2f deg, spread %.2f deg" % (edge, len(angles), med, spread))
        if best is None or spread < best[2]:
            best = (edge, med, spread)
    if best is None:
        need = "crank pickup" if prof.NAME == "22re" else "Ne and G1 inputs"
        sys.exit("No usable timing data. Check the %s and the IGT tap with probe." % need)
    edge, med, spread = best
    offset = (args.light + med) % prof.ANGLE_SPAN
    cal = {"offset_deg": round(offset, 2), "edge": edge, "light_reading_btdc": args.light,
           "spread_deg": round(spread, 2), "date": dt.date.today().isoformat()}
    path = decode.save_calibration(prof.NAME, cal)
    print("using %s edge. offset %.2f deg saved to %s" % (edge, offset, os.path.relpath(path)))
    if spread > 1.5:
        print("warning: spread over 1.5 deg. Idle may be unsteady or a pickup is noisy; recheck before trusting timing.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    engines = list(profiles.ENGINES)

    p = sub.add_parser("demo", help="synthetic run, no hardware")
    p.add_argument("--engine", required=True, choices=engines)
    p.add_argument("--seconds", type=float, default=45.0)
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("ports", help="list serial ports")
    p.set_defaults(func=cmd_ports)

    p = sub.add_parser("probe", help="1 s snapshot of every input")
    p.add_argument("--engine", required=True, choices=engines)
    p.add_argument("--port", required=True)
    p.add_argument("--sim", type=int, default=0, help="bench only: run the simulator at this rpm")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("ecu", help="1UZ: watch the VF1 diagnostic stream")
    p.add_argument("--port", required=True)
    p.add_argument("--seconds", type=int, default=20)
    p.add_argument("--invert", action="store_true", help="VF1 idles LOW on this setup")
    p.set_defaults(func=cmd_ecu)

    p = sub.add_parser("log", help="stream frames to logs/*.csv")
    p.add_argument("--engine", required=True, choices=engines)
    p.add_argument("--port", required=True)
    p.add_argument("--rate", type=int, default=50, help="frames per second (1-100)")
    p.add_argument("--sim", type=int, default=0, help="bench only: run the simulator at this rpm")
    p.add_argument("--seconds", type=float, default=None, help="stop after this long")
    p.add_argument("--name", default="", help="short tag for the file name, e.g. warm-idle")
    p.add_argument("--invert", action="store_true", help="1UZ: VF1 idles LOW on this setup")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("calibrate", help="set the timing offset from a timing light reading")
    p.add_argument("--engine", required=True, choices=engines)
    p.add_argument("--port", required=True)
    p.add_argument("--light", type=float, required=True, help="timing light reading, degrees BTDC")
    p.set_defaults(func=cmd_calibrate)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
