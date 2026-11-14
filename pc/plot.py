#!/usr/bin/env python3
"""Plot a log as stacked traces and save a PNG next to the CSV.

  python3 pc/plot.py logs/run_....csv [--from 20 --to 45]

Needs matplotlib (optional dependency).
"""

import argparse
import csv
import os
import sys


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


TRACES = [
    ("rpm", "rpm"),
    ("timing", "timing deg"),
    ("inj_ms", "inj ms"),
    ("ox", "O2 V"),
    ("ox2", "O2 bank 2 V"),
    ("airflow", "airflow"),
    ("vta", "VTA V"),
    ("idl_closed", "IDL closed"),
    ("batt", "+B V"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--from", dest="t0", type=float, default=None)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--show", action="store_true", help="open a window instead of only saving")
    args = ap.parse_args()
    try:
        import matplotlib
        if not args.show:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        sys.exit("matplotlib is missing: pip install matplotlib")

    with open(args.csv, newline="") as f:
        rows = list(csv.DictReader(f))
    t = [num(r["t_s"]) for r in rows]
    keep = [i for i, x in enumerate(t) if x is not None
            and (args.t0 is None or x >= args.t0) and (args.t1 is None or x <= args.t1)]
    t = [t[i] for i in keep]
    rows = [rows[i] for i in keep]
    calibrated = any(r["timing_btdc"] for r in rows)

    fig, axes = plt.subplots(len(TRACES), 1, sharex=True, figsize=(12, 2 + 1.3 * len(TRACES)))
    for ax, (key, label) in zip(axes, TRACES):
        if key == "timing":
            if calibrated:
                y = [num(r["timing_btdc"]) for r in rows]
            else:
                y = [None if num(r["spark_angle_raw"]) is None else -num(r["spark_angle_raw"]) for r in rows]
                label = "timing (uncal.)"
        else:
            if key not in rows[0]:
                ax.set_visible(False)
                continue
            y = [num(r.get(key)) for r in rows]
        ax.plot(t, [float("nan") if v is None else v for v in y], lw=0.8)
        ax.set_ylabel(label, fontsize=8)
        ax.grid(alpha=0.3)
        for r, x in zip(rows, t):
            if r.get("mark"):
                ax.axvline(x, color="tab:red", lw=0.8, alpha=0.6)
    for r, x in zip(rows, t):
        if r.get("mark"):
            axes[0].annotate("#%s %s" % (r["mark"], r.get("note", "")), (x, 1.0),
                             xycoords=("data", "axes fraction"), fontsize=7, color="tab:red",
                             rotation=90, va="top")
    axes[-1].set_xlabel("seconds")
    fig.suptitle(os.path.basename(args.csv), fontsize=10)
    fig.tight_layout()
    out = os.path.splitext(args.csv)[0] + ".png"
    fig.savefig(out, dpi=110)
    print("saved", out)
    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
