"""Toyota 1UZ-FE, non-VVTi (1990-94 LS400 / 1992-94 SC400 engine computer).

Sources: Toyota's 1UZ-FE new-car-features description (LS400):
  - Ne: 12-tooth signal plate on the crank, magnetic pickup (one tooth per 30 deg)
  - G1/G2: cam signal plate, once per 2 crank revs, pickups in the distributor housing
  - two igniters: IGT1 fires cylinders 1,4,6,7, IGT2 fires 2,3,5,8; spark when IGT goes off
  - four-group injection: each group feeds two cylinders, once every 2 revs
  - optical Karman-vortex airflow meter: a frequency signal (KS), not a voltage
  - base timing 10 deg BTDC with TE1-E1 jumped and the throttle closed
Plus the OBD1 serial stream on VF1 with TE2 jumped to E1 (see pc/vf1.py).
Every terminal still has to be checked against the EWD for the exact computer.
"""

import config
import decode
import vf1
from profiles import scenario

NAME = "1uz"
TITLE = "Toyota 1UZ-FE (non-VVTi)"
SKETCH = "arduino/logger1uz"
HAS_VF1 = True
ANGLE_SPAN = 180.0  # IGT1 drives 4 of 8 cylinders: a spark every 180 crank degrees
BASE_TIMING_NOTE = "TE1-E1 jumped, throttle closed: Toyota spec 10 deg BTDC"
NE_TEETH = 12

RAW_FIELDS = [
    "ms", "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7",
    "ne_us", "g1_teeth", "ig1_tooth_us", "ig1_toothp_us", "ig1_dwell_us", "ig1_us",
    "ig2_dwell_us", "ig2_us", "g1_ph_us", "g1_toothp_us", "inj_us", "inj_n", "ks_n", "ks_span_us",
]

CHANNELS = [
    ("vta", "VTA throttle position", 1.0),
    ("idl", "IDL throttle idle contact", config.DIV_47_15),
    ("thw", "THW coolant temp sensor", 1.0),
    ("tha", "THA intake air temp sensor", 1.0),
    ("ox", "OX1 main O2 sensor, bank 1", 1.0),
    ("ox2", "OX2 main O2 sensor, bank 2", 1.0),
    ("batt", "+B ECU supply", config.DIV_47_15),
    ("vf1_v", "VF1 data line level", config.DIV_47_15),
]

EXTRA_FIELDS = ["ox2", "vta", "idl", "thw", "tha", "vf1_v", "dwell2_ms", "ig2_ok", "g1_phase_deg"] + vf1.ECU_FIELDS
PROBE_NAMES = {
    "D2": "Ne crank (comparator)", "D3": "IGT1", "D4": "IGT2", "D5": "injector group",
    "D6": "KS airflow", "D7": "G1 cam (comparator)", "D8": "VF1 data",
}
SIM_JUMPERS = "D9-D2 (Ne), D10-D7 (G1), D11-D3 (IGT1), D12-D5 (injector), D13-D6 (KS)"
NO_G1 = 255


def spark_angle(raw, edge="fall"):
    """Crank degrees from G1 to the IGT1 spark edge, folded to [0, 180). Needs G1."""
    teeth, since, period = raw["g1_teeth"], raw["ig1_tooth_us"], raw["ig1_toothp_us"]
    if teeth == NO_G1 or not period:
        return None
    return (teeth * 30.0 + since / period * 30.0) % ANGLE_SPAN


def convert(raw, cal=None, t0_ms=0):
    row = {"t_s": round((raw["ms"] - t0_ms) / 1000.0, 3), "mark": "", "note": ""}
    if raw["ne_us"]:
        rpm = 60e6 / (NE_TEETH * raw["ne_us"])
    elif raw["ig1_us"]:
        rpm = 60e6 / (raw["ig1_us"] * 2)
    else:
        rpm = 0.0
    row["rpm"] = round(rpm)
    ang = spark_angle(raw)
    row["spark_angle_raw"] = "" if ang is None else round(ang, 2)
    if ang is not None and cal and "offset_deg" in cal:
        row["timing_btdc"] = round(decode.timing_from_angle(ang, cal["offset_deg"], ANGLE_SPAN), 2)
    else:
        row["timing_btdc"] = ""
    row["dwell_ms"] = round(raw["ig1_dwell_us"] / 1000.0, 2) if raw["ig1_dwell_us"] else ""
    row["dwell2_ms"] = round(raw["ig2_dwell_us"] / 1000.0, 2) if raw["ig2_dwell_us"] else ""
    # both igniters should fire at the same rate; a dead one shows here first
    row["ig2_ok"] = int(bool(raw["ig1_us"]) == bool(raw["ig2_us"]))
    row["g1_phase_deg"] = round(raw["g1_ph_us"] / raw["g1_toothp_us"] * 30.0, 2) if raw["g1_toothp_us"] else ""
    row["inj_ms"] = round(raw["inj_us"] / 1000.0, 3) if raw["inj_n"] else ""
    row["inj_n"] = raw["inj_n"]
    if raw["ks_n"] >= 2 and raw["ks_span_us"]:
        row["airflow"] = round((raw["ks_n"] - 1) / raw["ks_span_us"] * 1e6, 1)
    else:
        row["airflow"] = ""
    row.update(decode.analog_volts(raw, CHANNELS))
    row["idl_closed"] = 1 if row["idl"] < config.IDL_CLOSED_BELOW_V else 0
    for k in vf1.ECU_FIELDS:
        row[k] = ""
    return row


DEMO_CAL = {"offset_deg": 0.0, "source": "demo"}


def _counts(v, divider):
    return max(0, min(1023, round(v / divider / config.NANO_VCC * 1023)))


def _ecu_bytes(s):
    holding = s["holding"]
    return [
        0,
        min(255, round(s["inj_ms"] / 0.125)),
        min(255, max(0, round((s["timing"] + 30) / 0.47))),
        77 if not holding else 60,
        min(255, round(s["rpm"] / 25)),
        min(255, round(40 + 150 * s["load"])),
        230,                                   # about 85 C
        36 if holding else 0,
        0,
        128, 128,
        (0 if holding else 1 << 5),            # closed loop at idle
        (0 if holding else 1 << 1),            # idle contact
        1 << 3,                                # neutral
        (1 << 4) if s["ox"] > 0.45 else 0,
    ]


def demo_lines(seconds=45.0):
    """D frames at 50 Hz plus VF1 edges for a frame every ~1.7 s, merged in time order."""
    yield "H," + ",".join(RAW_FIELDS)
    edges = []      # pending (t_us, level)
    next_vf1 = 0.5  # seconds
    level = 1
    for s in scenario.states(seconds, base_timing=10.0):
        t = s["t"]
        if t >= next_vf1:
            frame_edges, t_end_us = vf1.encode(0x0, _ecu_bytes(s), t0=round(t * 1e6))
            for te, lv in frame_edges:
                if lv != level:
                    edges.append((te, lv))
                    level = lv
            next_vf1 = t_end_us / 1e6 + 0.05
        while edges and edges[0][0] <= t * 1e6:
            te, lv = edges.pop(0)
            yield "E,%d,%d" % (te & 0xFFFFFFFF, lv)
        rnd = s["rnd"]
        volts = {
            "vta": 3.0 if s["holding"] else 0.6,
            "idl": 11.8 if s["holding"] else 0.05,
            "thw": 0.55, "tha": 2.0, "ox": s["ox"], "ox2": s["ox2"],
            "batt": 14.0 + rnd.gauss(0, 0.03),
            "vf1_v": 4.8 if level else 0.1,
        }
        tooth = 60e6 / (NE_TEETH * s["rpm"])
        angle = (DEMO_CAL["offset_deg"] - s["timing"]) % ANGLE_SPAN
        ig1_us = 60e6 / s["rpm"] / 2
        ks_hz = 40 + 900 * s["load"] * s["rpm"] / 3000
        ks_n = max(2, round(ks_hz / scenario.RATE_HZ))
        raw = {
            "ms": round(t * 1000),
            "ne_us": round(tooth),
            "g1_teeth": int(angle // 30),
            "ig1_tooth_us": round((angle % 30) / 30 * tooth),
            "ig1_toothp_us": round(tooth),
            "ig1_dwell_us": 3000, "ig1_us": round(ig1_us),
            "ig2_dwell_us": 3000, "ig2_us": round(ig1_us),
            "g1_ph_us": round(0.5 * tooth), "g1_toothp_us": round(tooth),
            "inj_us": round(s["inj_ms"] * 1000),
            "inj_n": max(1, round(s["rpm"] / 120.0 / scenario.RATE_HZ)),
            "ks_n": ks_n,
            "ks_span_us": round((ks_n - 1) / ks_hz * 1e6),
        }
        for i, (key, _l, div) in enumerate(CHANNELS):
            raw["a%d" % i] = _counts(volts[key], div)
        yield "D," + ",".join(str(raw[k]) for k in RAW_FIELDS)
