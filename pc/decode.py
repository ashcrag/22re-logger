"""Engine-independent parsing: firmware lines, calibration files, timing math."""

import json
import os

import config

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Columns every profile writes, in this order, before its own extras.
COMMON_FIELDS = [
    "t_s", "mark", "note", "rpm", "timing_btdc", "spark_angle_raw",
    "dwell_ms", "inj_ms", "inj_n", "airflow", "ox", "batt", "idl_closed",
]


def calibration_path(engine):
    return os.path.join(REPO_ROOT, "calibration_%s.json" % engine)


def load_calibration(engine):
    try:
        with open(calibration_path(engine)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_calibration(engine, cal):
    path = calibration_path(engine)
    with open(path, "w") as f:
        json.dump(cal, f, indent=2)
    return path


def parse_header(line):
    """'H,ms,a0,...' -> list of field names, else None."""
    line = line.strip()
    if not line.startswith("H,"):
        return None
    return line.split(",")[1:]


def parse(line, fields):
    """'D,...' frame -> dict of ints keyed by fields, else None."""
    line = line.strip()
    if not line.startswith("D,"):
        return None
    parts = line.split(",")[1:]
    if len(parts) != len(fields):
        return None
    try:
        return dict(zip(fields, (int(p) for p in parts)))
    except ValueError:
        return None


def parse_edge(line):
    """'E,<micros>,<level>' VF1 edge -> (t_us, level), else None."""
    line = line.strip()
    if not line.startswith("E,"):
        return None
    try:
        _, t, lvl = line.split(",")
        return int(t), int(lvl)
    except ValueError:
        return None


def counts_to_volts(counts, divider):
    return counts / 1023.0 * config.NANO_VCC * divider


def timing_from_angle(angle, offset_deg, span=180.0):
    """Spark advance in degrees BTDC from a raw angle, range (-span/2, span/2]."""
    x = (offset_deg - angle) % span
    return x - span if x > span / 2 else x


def analog_volts(raw, channels):
    """{key: volts} for a profile's (key, label, divider) channel list in pin order."""
    return {key: round(counts_to_volts(raw["a%d" % i], div), 3) for i, (key, _l, div) in enumerate(channels)}
