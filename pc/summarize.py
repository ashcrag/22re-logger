#!/usr/bin/env python3
"""Summarize a log: idle baseline, then every rev-hold-release event.

  python3 pc/summarize.py logs/run_....csv [--rev-rpm 2000] [--min-hold 1.0]

Reports what the signals did. It does not diagnose.
"""

import argparse
import csv
import statistics
import sys

import config


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        d = {k: num(v) for k, v in r.items() if k not in ("note",)}
        d["note"] = r.get("note", "")
        # timing: calibrated if present, else the negated raw angle (same deltas, unknown zero)
        if d.get("timing_btdc") is not None:
            d["tm"] = d["timing_btdc"]
        elif d.get("spark_angle_raw") is not None:
            d["tm"] = -d["spark_angle_raw"]
        else:
            d["tm"] = None
        out.append(d)
    return out


def vals(rows, key):
    return [r[key] for r in rows if r.get(key) is not None]


def med(rows, key):
    v = vals(rows, key)
    return statistics.median(v) if v else None


def mean(rows, key):
    v = vals(rows, key)
    return statistics.fmean(v) if v else None


def circ_delta(a, b):
    """a - b for timing values, safe across the 180 deg fold."""
    return ((a - b + 90.0) % 180.0) - 90.0


def window(rows, t0, t1):
    return [r for r in rows if r["t_s"] is not None and t0 <= r["t_s"] < t1]


def find_events(rows, rev_rpm, min_hold):
    events = []
    i, n = 0, len(rows)
    while i < n:
        if (rows[i]["rpm"] or 0) >= rev_rpm:
            j = i
            while j < n and (rows[j]["rpm"] or 0) >= rev_rpm:
                j += 1
            start, end = rows[i]["t_s"], rows[min(j, n - 1)]["t_s"]
            if end - start >= min_hold:
                events.append((start, end))
            i = j
        else:
            i += 1
    return events


def fmt(v, spec="%.1f", none="n/a"):
    return none if v is None else spec % v


def settle_time(rows, t_release, base_rpm, until):
    """Seconds after release until rpm stays within +-10% of baseline for 2 s."""
    post = window(rows, t_release, until)
    band = 0.10 * base_rpm
    run_start = None
    for r in post:
        if r["rpm"] is not None and abs(r["rpm"] - base_rpm) <= band:
            if run_start is None:
                run_start = r["t_s"]
            if r["t_s"] - run_start >= 2.0:
                return run_start - t_release
        else:
            run_start = None
    return None


def pct(rows, key):
    v = [r[key] for r in rows if r.get(key) is not None]
    return None if not v else sum(1 for x in v if x == 1) / len(v) * 100


def summarize_1uz(rows, idle):
    """1UZ extras: engine computer stream, second igniter, cam/crank phase."""
    frames = [r for r in rows if r.get("ecu_age_s") is not None and r["ecu_age_s"] == 0.0]
    print("\nengine computer stream (VF1): %d frames" % len(frames))
    if not frames:
        print("  none decoded: TE2 not jumped, VF1 not tapped, or the stream isn't there on this computer")
    else:
        last = frames[-1]
        print("  last frame: rpm %s, ect %s C, tps %s%%, timing %s, inj %s ms, iac %s%%" % (
            fmt(last.get("ecu_rpm"), "%.0f"), fmt(last.get("ecu_ect_c"), "%.0f"), fmt(last.get("ecu_tps_pct"), "%.0f"),
            fmt(last.get("ecu_timing"), "%.1f"), fmt(last.get("ecu_inj_ms"), "%.2f"), fmt(last.get("ecu_iac_pct"), "%.0f")))
        idle_frames = [r for r in idle if r.get("ecu_age_s") == 0.0]
        for key, label in (("ecu_closed_loop", "closed loop"), ("ecu_idle", "idle flag"),
                           ("ecu_neutral", "neutral flag"), ("ecu_knock", "knock flag"), ("ecu_ac", "A/C flag")):
            p = pct(idle_frames, key)
            if p is not None:
                print("  at idle, %s set in %.0f%% of frames" % (label, p))
        pairs = [(r["ecu_rpm"], r["rpm"]) for r in frames if r.get("ecu_rpm") and r.get("rpm")]
        if pairs:
            diff = statistics.median(abs(a - b) for a, b in pairs)
            print("  ECU rpm vs measured rpm: median difference %.0f rpm%s" % (
                diff, "  (byte map may be off for this computer)" if diff > 150 else ""))
        print("  note: the byte map is from 4-cylinder Toyotas and unverified on the 1UZ; check against known values")
    bad = [r for r in rows if r.get("ig2_ok") == 0 and (r.get("rpm") or 0) > 0]
    if bad:
        print("  igniters: IGT1 and IGT2 disagree in %d rows (one igniter line dead or untapped)" % len(bad))
    ph = vals(idle, "g1_phase_deg")
    if ph:
        print("  G1 cam vs Ne crank phase at idle: median %.1f deg, spread %.1f deg (compare with a known-good engine)" % (
            statistics.median(ph), statistics.pstdev(ph)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--rev-rpm", type=float, default=2000, help="rpm that counts as a held rev")
    ap.add_argument("--min-hold", type=float, default=1.0, help="seconds above rev-rpm to count")
    ap.add_argument("--after", type=float, default=15.0, help="seconds after release to examine")
    args = ap.parse_args()

    rows = [r for r in load(args.csv) if r["t_s"] is not None]
    if not rows:
        sys.exit("no rows")
    is_1uz = "ecu_raw" in rows[0]
    air_unit = "Hz (KS)" if is_1uz else "V (VS)"
    print("file: %s" % args.csv)
    print("duration %.1f s, %d rows" % (rows[-1]["t_s"] - rows[0]["t_s"], len(rows)))
    have_timing = any(r["tm"] is not None for r in rows)
    calibrated = any(r.get("timing_btdc") is not None for r in rows)
    if not have_timing:
        print("timing: no crank pickup data in this log")
    elif not calibrated:
        print("timing: not calibrated, so only changes (deltas) are meaningful, not absolute degrees")

    marks = [r for r in rows if r.get("mark") is not None]
    if marks:
        print("markers:")
        for r in marks:
            print("  #%d at %.1f s  %s" % (r["mark"], r["t_s"], r["note"]))

    events = find_events(rows, args.rev_rpm, args.min_hold)
    first_rev = events[0][0] if events else rows[-1]["t_s"]
    # stay 1 s clear of the ramp up into a rev
    idle = [r for r in window(rows, rows[0]["t_s"], first_rev - 1.0) if r["rpm"] and r["rpm"] < args.rev_rpm]
    base_rpm = med(idle, "rpm")
    print("\nidle before first rev (%d rows)" % len(idle))
    if base_rpm:
        rpms = vals(idle, "rpm")
        print("  rpm median %.0f, range %.0f-%.0f" % (base_rpm, min(rpms), max(rpms)))
    print("  timing %s deg   inj %s ms   airflow %s %s   batt %s V" % (
        fmt(med(idle, "tm")), fmt(mean(idle, "inj_ms"), "%.2f"), fmt(mean(idle, "airflow"), "%.2f"),
        air_unit, fmt(mean(idle, "batt"), "%.1f")))
    for key in ("ox", "ox2"):
        oxs = vals(idle, key)
        if oxs:
            lean = sum(1 for v in oxs if v < config.OX_SWITCH_V) / len(oxs) * 100
            print("  %s mean %.2f V, below %.2f V (lean side) %.0f%% of the time" % (
                key, statistics.fmean(oxs), config.OX_SWITCH_V, lean))
    if is_1uz:
        summarize_1uz(rows, idle)

    if not events:
        print("\nno rev events above %.0f rpm held %.1f s" % (args.rev_rpm, args.min_hold))
        return

    for k, (start, release) in enumerate(events, 1):
        nxt = events[k][0] if k < len(events) else rows[-1]["t_s"] + 1
        until = min(release + args.after, nxt - 1.0)
        pre = [r for r in window(rows, start - 6.0, start - 1.0) if r["rpm"] and r["rpm"] < args.rev_rpm]
        hold = window(rows, start, release)
        post = window(rows, release, until)
        early = window(rows, release, release + 3.0)
        b_rpm = med(pre, "rpm") or base_rpm
        b_tm = med(pre, "tm")
        print("\nevent %d: held %.1f s above %.0f rpm (%.1f-%.1f s), hold rpm median %s" % (
            k, release - start, args.rev_rpm, start, release, fmt(med(hold, "rpm"), "%.0f")))
        if not post:
            print("  log ends at release")
            continue
        low = min(post, key=lambda r: r["rpm"] if r["rpm"] is not None else 1e9)
        print("  after release: lowest rpm %.0f at +%.1f s (baseline %s)" % (
            low["rpm"], low["t_s"] - release, fmt(b_rpm, "%.0f")))
        if b_rpm:
            st = settle_time(rows, release, b_rpm, until)
            print("  back within 10%% of baseline and steady: %s" % (
                "+%.1f s" % st if st is not None else "not within %.0f s window" % (until - release)))
        stalled = [r for r in post if r["rpm"] == 0]
        if stalled:
            print("  ENGINE STOPPED at +%.1f s" % (stalled[0]["t_s"] - release))
        e_tm = med(early, "tm")
        if b_tm is not None and e_tm is not None:
            post_tm = vals(post, "tm")
            worst = max(post_tm, key=lambda v: abs(circ_delta(v, b_tm)))
            print("  timing: first 3 s median %+.1f deg vs pre-rev idle, largest swing %+.1f deg" % (
                circ_delta(e_tm, b_tm), circ_delta(worst, b_tm)))
        e_inj, b_inj = mean(early, "inj_ms"), mean(pre, "inj_ms")
        if e_inj is not None and b_inj:
            print("  injector: first 3 s %.2f ms vs %.2f ms pre-rev (%+.0f%%)" % (
                e_inj, b_inj, (e_inj / b_inj - 1) * 100))
        e_ox = vals(early, "ox")
        if e_ox:
            lean = sum(1 for v in e_ox if v < config.OX_SWITCH_V) / len(e_ox) * 100
            print("  ox: first 3 s mean %.2f V, lean side %.0f%% of the time" % (statistics.fmean(e_ox), lean))
        e_air, b_air = mean(early, "airflow"), mean(pre, "airflow")
        if e_air is not None and b_air is not None:
            print("  airflow: first 3 s %.2f vs %.2f %s pre-rev" % (e_air, b_air, air_unit))
        idl_open = [r for r in post if r.get("idl_closed") == 0]
        if idl_open and len(idl_open) < len(post):
            print("  idl: open for %.1f s of the window after release" % (len(idl_open) / len(post) * (until - release)))
        b = vals(post, "batt")
        if b:
            print("  batt: min %.1f V" % min(b))

    if have_timing:
        jumper = "TE1-E1" if is_1uz else "T-E1"
        print("\nnote: without the %s jumper the ECU changes timing on its own after a rev," % jumper)
        print("so a timing swing alone does not separate ECU command from a mechanical cause.")
        print("Run the jumpered test in the engine's docs/<engine>/test-plan.md for that.")


if __name__ == "__main__":
    main()
