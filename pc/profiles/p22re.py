"""Toyota 22R-E (1985-88 EFI 4-cylinder). The ECU has no data link, so
everything comes from tapped wires plus a hall pickup on the balancer."""

import config
import decode
from profiles import scenario

NAME = "22re"
TITLE = "Toyota 22R-E"
SKETCH = "arduino/logger22re"
HAS_VF1 = False
ANGLE_SPAN = 180.0  # one IGT line, 4 cylinders: a spark every 180 crank degrees
BASE_TIMING_NOTE = "T-E1 jumped at the check connector; confirm the base value in the repair manual"

RAW_FIELDS = [
    "ms", "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7",
    "crank_us", "igt_us", "dwell_us", "rise_ac_us", "fall_ac_us",
    "spark_crank_us", "inj_us", "inj_n",
]

# (key, label, divider) for A0..A7. divider = signal volts / pin volts.
CHANNELS = [
    ("airflow", "VS airflow meter signal", 1.0),
    ("vta", "VTA throttle position", 1.0),
    ("idl", "IDL throttle idle contact", config.DIV_47_15),
    ("thw", "THW coolant temp sensor", 1.0),
    ("tha", "THA intake air temp sensor", 1.0),
    ("ox", "OX oxygen sensor", 1.0),
    ("batt", "+B ECU supply", config.DIV_47_15),
    ("spare", "spare (A7)", 1.0),
]

EXTRA_FIELDS = ["vta", "idl", "thw", "tha", "spare"]
PROBE_NAMES = {"D2": "crank pickup", "D3": "IGT", "D4": "injector"}
SIM_JUMPERS = "D9-D2, D10-D3, D11-D4"


def spark_angle(raw, edge="fall"):
    """Crank degrees from the pickup to the spark edge, folded to [0, 180)."""
    if edge == "fall":
        us, period = raw["fall_ac_us"], raw["spark_crank_us"]
    else:
        us, period = raw["rise_ac_us"], raw["crank_us"]
    if not us or not period:
        return None
    return (us / period * 360.0) % ANGLE_SPAN


def convert(raw, cal=None, t0_ms=0):
    row = {"t_s": round((raw["ms"] - t0_ms) / 1000.0, 3), "mark": "", "note": ""}
    if raw["crank_us"]:
        rpm = 60e6 / raw["crank_us"]
    elif raw["igt_us"]:
        rpm = 60e6 / (raw["igt_us"] * 2)
    else:
        rpm = 0.0
    row["rpm"] = round(rpm)
    ang = spark_angle(raw, (cal or {}).get("edge", "fall"))
    row["spark_angle_raw"] = "" if ang is None else round(ang, 2)
    if ang is not None and cal and "offset_deg" in cal:
        row["timing_btdc"] = round(decode.timing_from_angle(ang, cal["offset_deg"], ANGLE_SPAN), 2)
    else:
        row["timing_btdc"] = ""
    row["dwell_ms"] = round(raw["dwell_us"] / 1000.0, 2) if raw["dwell_us"] else ""
    row["inj_ms"] = round(raw["inj_us"] / 1000.0, 3) if raw["inj_n"] else ""
    row["inj_n"] = raw["inj_n"]
    row.update(decode.analog_volts(raw, CHANNELS))
    row["idl_closed"] = 1 if row["idl"] < config.IDL_CLOSED_BELOW_V else 0
    return row


DEMO_CAL = {"offset_deg": 0.0, "edge": "fall", "source": "demo"}


def _counts(v, divider):
    return max(0, min(1023, round(v / divider / config.NANO_VCC * 1023)))


def demo_lines(seconds=45.0):
    yield "H," + ",".join(RAW_FIELDS)
    for s in scenario.states(seconds, base_timing=12.0):
        rnd = s["rnd"]
        volts = {
            "airflow": (2.2 if s["holding"] else 3.6) + rnd.gauss(0, 0.02),
            "vta": 3.2 if s["holding"] else 0.55,
            "idl": 11.8 if s["holding"] else 0.05,
            "thw": 0.62, "tha": 2.1, "ox": s["ox"],
            "batt": 14.1 + rnd.gauss(0, 0.03), "spare": 0.0,
        }
        crank_us = round(60e6 / s["rpm"])
        angle = (DEMO_CAL["offset_deg"] - s["timing"]) % ANGLE_SPAN
        raw = {
            "ms": round(s["t"] * 1000),
            "crank_us": crank_us,
            "igt_us": round(crank_us / 2),
            "dwell_us": 3000,
            "rise_ac_us": round((angle - 15.0) % ANGLE_SPAN / 360.0 * crank_us),
            "fall_ac_us": round(angle / 360.0 * crank_us),
            "spark_crank_us": crank_us,
            "inj_us": round(s["inj_ms"] * 1000),
            "inj_n": max(1, round(s["rpm"] / 60.0 / scenario.RATE_HZ)),
        }
        for i, (key, _l, div) in enumerate(CHANNELS):
            raw["a%d" % i] = _counts(volts[key], div)
        yield "D," + ",".join(str(raw[k]) for k in RAW_FIELDS)
