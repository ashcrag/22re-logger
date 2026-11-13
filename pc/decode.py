"""Parse firmware frames and turn raw counts into engineering values."""

import json
import os

import config

RAW_FIELDS = [
    "ms", "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7",
    "crank_us", "igt_us", "dwell_us", "rise_ac_us", "fall_ac_us",
    "spark_crank_us", "inj_us", "inj_n",
]

CSV_FIELDS = (
    ["t_s", "mark", "note", "rpm", "timing_btdc", "spark_angle_raw", "dwell_ms", "inj_ms", "inj_n"]
    + [key for key, _, _ in config.CHANNELS]
    + ["idl_closed"]
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_calibration():
    path = os.path.join(REPO_ROOT, config.CALIBRATION_FILE)
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_calibration(cal):
    path = os.path.join(REPO_ROOT, config.CALIBRATION_FILE)
    with open(path, "w") as f:
        json.dump(cal, f, indent=2)
    return path


def parse(line):
    """Return a dict of ints for a D frame, else None."""
    line = line.strip()
    if not line.startswith("D,"):
        return None
    parts = line.split(",")[1:]
    if len(parts) != len(RAW_FIELDS):
        return None
    try:
        return dict(zip(RAW_FIELDS, (int(p) for p in parts)))
    except ValueError:
        return None


def counts_to_volts(counts, divider):
    return counts / 1023.0 * config.NANO_VCC * divider


def spark_angle(raw, edge="fall"):
    """Degrees of crank rotation from the crank pickup to the spark edge, folded to 0-180.

    Returns None when there is no crank pickup signal or no IGT.
    """
    if edge == "fall":
        us, period = raw["fall_ac_us"], raw["spark_crank_us"]
    else:
        us, period = raw["rise_ac_us"], raw["crank_us"]
    if not us or not period:
        return None
    return (us / period * 360.0) % 180.0


def timing_from_angle(angle, offset_deg):
    """Spark advance in degrees BTDC, range (-90, 90]."""
    x = (offset_deg - angle) % 180.0
    return x - 180.0 if x > 90.0 else x


def convert(raw, cal=None, t0_ms=0):
    row = {"t_s": round((raw["ms"] - t0_ms) / 1000.0, 3)}
    if raw["crank_us"]:
        rpm = 60e6 / raw["crank_us"]
    elif raw["igt_us"]:
        rpm = 60e6 / (raw["igt_us"] * config.IGT_PER_REV)
    else:
        rpm = 0.0
    row["rpm"] = round(rpm)
    edge = (cal or {}).get("edge", "fall")
    ang = spark_angle(raw, edge)
    row["spark_angle_raw"] = "" if ang is None else round(ang, 2)
    if ang is not None and cal and "offset_deg" in cal:
        row["timing_btdc"] = round(timing_from_angle(ang, cal["offset_deg"]), 2)
    else:
        row["timing_btdc"] = ""
    row["dwell_ms"] = round(raw["dwell_us"] / 1000.0, 2) if raw["dwell_us"] else ""
    row["inj_ms"] = round(raw["inj_us"] / 1000.0, 3) if raw["inj_n"] else ""
    row["inj_n"] = raw["inj_n"]
    for i, (key, _label, divider) in enumerate(config.CHANNELS):
        row[key] = round(counts_to_volts(raw["a%d" % i], divider), 3)
    row["idl_closed"] = 1 if row["idl"] < config.IDL_CLOSED_BELOW_V else 0
    row["mark"] = ""
    row["note"] = ""
    return row
