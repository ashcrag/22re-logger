"""Made-up engine behaviour shared by every profile's demo.

Warm idle with two rev-and-release events; the idle stumbles after each
release, worse after the longer hold, with timing sagging and O2 going
lean. Every value is synthetic and says nothing about a real engine.
"""

import math
import random

RATE_HZ = 50
REVS = [(8.0, 14.0), (24.0, 34.0)]  # (start_s, release_s)
IDLE_RPM = 800.0
HOLD_RPM = 3000.0


def _rpm(t):
    for start, end in REVS:
        if start <= t < start + 1.0:
            return IDLE_RPM + (HOLD_RPM - IDLE_RPM) * (t - start)
        if start + 1.0 <= t < end:
            return HOLD_RPM
        if end <= t < end + 8.0:
            dt = t - end
            dip = 250.0 + 25.0 * (end - start)
            if dt < 0.6:
                return HOLD_RPM - (HOLD_RPM - (IDLE_RPM - dip)) * (dt / 0.6)
            return IDLE_RPM - dip * math.exp(-(dt - 0.6) / 1.8)
    return IDLE_RPM


def _after_release(t):
    for start, end in REVS:
        if end <= t < end + 8.0:
            return t - end, end - start
    return None, None


def states(seconds=45.0, seed=1, base_timing=12.0):
    """Yield one dict per frame: t, rpm, timing, ox, ox2, inj_ms, airflow (0-1 load), holding."""
    rnd = random.Random(seed)
    for i in range(int(seconds * RATE_HZ)):
        t = i / RATE_HZ
        rpm = max(300.0, _rpm(t) + rnd.gauss(0, 8))
        holding = any(s <= t < e for s, e in REVS)
        dt, hold = _after_release(t)
        timing = base_timing + 18.0 if holding else base_timing
        ox = 0.45 + 0.35 * math.sin(2 * math.pi * t)
        ox2 = 0.45 + 0.35 * math.sin(2 * math.pi * 0.9 * t + 1.0)
        inj = 3.1 if holding else 2.4
        load = 0.6 if holding else 0.15
        if dt is not None:
            timing -= (2.0 + 0.4 * hold) * math.exp(-dt / 2.5)
            if dt < 2.5:
                ox = ox2 = 0.08
            inj -= 0.4 * math.exp(-dt / 1.5)
        yield {
            "t": t,
            "rpm": rpm,
            "timing": timing + rnd.gauss(0, 0.3),
            "ox": min(0.95, max(0.02, ox + rnd.gauss(0, 0.02))),
            "ox2": min(0.95, max(0.02, ox2 + rnd.gauss(0, 0.02))),
            "inj_ms": inj,
            "load": load,
            "holding": holding,
            "rnd": rnd,
        }
