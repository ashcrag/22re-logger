"""Synthetic firmware frames for testing the laptop side without a Nano.

The data is made up. It imitates a warm idle with two rev-and-release
events where the idle stumbles afterwards, so every tool has something
to chew on. It says nothing about any real engine.
"""

import math
import random

import config

RATE_HZ = 50
DEMO_CAL = {"offset_deg": 0.0, "edge": "fall", "source": "demo"}

# (start_s, end_s) of each held rev; release happens at end_s
REVS = [(8.0, 14.0), (24.0, 34.0)]
IDLE_RPM = 800.0
HOLD_RPM = 3000.0


def _rpm(t):
    for start, end in REVS:
        if start <= t < start + 1.0:
            return IDLE_RPM + (HOLD_RPM - IDLE_RPM) * (t - start)
        if start + 1.0 <= t < end:
            return HOLD_RPM
        hold = end - start
        if end <= t < end + 8.0:
            dt = t - end
            dip = 250.0 + 25.0 * hold  # longer hold, deeper stumble
            if dt < 0.6:
                return HOLD_RPM - (HOLD_RPM - (IDLE_RPM - dip)) * (dt / 0.6)
            return IDLE_RPM - dip * math.exp(-(dt - 0.6) / 1.8)
    return IDLE_RPM


def _after_release(t):
    for start, end in REVS:
        if end <= t < end + 8.0:
            return t - end, end - start
    return None, None


def _volts_to_counts(v, divider):
    c = round(v / divider / config.NANO_VCC * 1023)
    return max(0, min(1023, c))


def frames(seconds=45.0, seed=1):
    rnd = random.Random(seed)
    n = int(seconds * RATE_HZ)
    for i in range(n):
        t = i / RATE_HZ
        rpm = max(300.0, _rpm(t) + rnd.gauss(0, 8))
        holding = any(s <= t < e for s, e in REVS)
        dt, hold = _after_release(t)

        timing = 30.0 if holding else 12.0
        ox = 0.45 + 0.35 * math.sin(2 * math.pi * 1.0 * t)
        inj_ms = 3.1 if holding else 2.4
        vs = 2.2 if holding else 3.6
        if dt is not None:
            lag = (2.0 + 0.4 * hold) * math.exp(-dt / 2.5)
            timing -= lag
            if dt < 2.5:
                ox = 0.08
            inj_ms -= 0.4 * math.exp(-dt / 1.5)
        timing += rnd.gauss(0, 0.3)
        ox = min(0.95, max(0.02, ox + rnd.gauss(0, 0.02)))

        volts = {
            "vs": vs + rnd.gauss(0, 0.02),
            "vta": 3.2 if holding else 0.55,
            "idl": 0.05 if not holding else 11.8,
            "thw": 0.62,
            "tha": 2.1,
            "ox": ox,
            "batt": 14.1 + rnd.gauss(0, 0.03),
            "spare": 0.0,
        }
        crank_us = round(60e6 / rpm)
        angle = (DEMO_CAL["offset_deg"] - timing) % 180.0
        raw = {
            "ms": round(t * 1000),
            "crank_us": crank_us,
            "igt_us": round(crank_us / config.IGT_PER_REV),
            "dwell_us": 3000,
            "rise_ac_us": round((angle - 15.0) % 180.0 / 360.0 * crank_us),
            "fall_ac_us": round(angle / 360.0 * crank_us),
            "spark_crank_us": crank_us,
            "inj_us": round(inj_ms * 1000),
            "inj_n": max(1, round(rpm / 60.0 / RATE_HZ)),
        }
        for idx, (key, _label, divider) in enumerate(config.CHANNELS):
            raw["a%d" % idx] = _volts_to_counts(volts[key], divider)
        yield raw
