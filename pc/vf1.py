"""Toyota OBD1 serial stream on VF1 (TE2 jumped to E1).

Bit level protocol, as decoded by the community (talofer99 / GadgetFreak,
hyperion11/toyota-obd-1):
  - about 8 ms per bit
  - line idles at the mark level (HIGH) for 15+ bit times between frames
  - frame: 4-bit ID (LSB first), then up to 24 bytes, each one
    start bit (LOW), 8 data bits LSB first, 2 stop bits (HIGH)

Byte meanings below come from 4-cylinder Corolla/Carina work. They are
UNVERIFIED for the 1UZ-FE: confirm each one against a known value
(rpm, coolant temp, throttle) before trusting it.
"""

BIT_US = 8000
MAX_BYTES = 24
IDLE_BITS = 15


class VF1Decoder:
    """Feed edges in time order; returns (id, [bytes]) when a frame completes.

    t_us is a free-running microsecond counter (wraps at 2**32), level is the
    line level right after the edge. invert=True for a setup where the line
    idles LOW.
    """

    def __init__(self, invert=False, bit_us=BIT_US):
        self.invert = invert
        self.bit_us = bit_us
        self.in_packet = False
        self.start = None
        self.bitcount = 0
        self.ident = 0
        self.data = [0] * MAX_BYTES
        self.fails = 0
        self.frames = 0

    def _elapsed(self, t):
        return (t - self.start) & 0xFFFFFFFF

    def edge(self, t_us, level):
        high = bool(level) != self.invert
        if not self.in_packet:
            if high:
                self.start = t_us
            elif self.start is not None and self._elapsed(t_us) > IDLE_BITS * self.bit_us:
                self.start = t_us
                self.in_packet = True
                self.bitcount = 0
            return None
        bits = int(self._elapsed(t_us) / self.bit_us + 0.5)
        self.start = t_us
        prev_high = not high  # level that was held during the span just ended
        while bits > 0:
            if self.bitcount < 4:
                if self.bitcount == 0:
                    self.ident = 0
                self.ident >>= 1
                if prev_high:
                    self.ident |= 0x08
            else:
                bitpos = (self.bitcount - 4) % 11
                bytepos = (self.bitcount - 4) // 11
                if bitpos == 0:
                    if self.bitcount > 4 and prev_high:  # start bit must be LOW
                        return self._fail()
                elif bitpos < 9:
                    self.data[bytepos] >>= 1
                    if prev_high:
                        self.data[bytepos] |= 0x80
                else:
                    if not prev_high:  # stop bits must be HIGH
                        return self._fail()
                    if bitpos == 10 and (bits > 1 or bytepos == MAX_BYTES - 1):
                        frame = (self.ident, list(self.data[: bytepos + 1]))
                        self.frames += 1
                        if bits >= 16:
                            self.bitcount = 0  # long HIGH was the next preamble
                        else:
                            self.in_packet = False
                        return frame
            self.bitcount += 1
            bits -= 1
        return None

    def _fail(self):
        self.fails += 1
        self.in_packet = False
        return None


def encode(ident, data, bit_us=BIT_US, t0=0, idle_bits=20):
    """Make (t_us, level) edges for one frame plus surrounding idle. For tests and demo.

    A frame is only detectable by the falling edge that ends the idle, so the
    first ID bit (bit 0) is always LOW in a real stream.
    """
    if ident & 1:
        raise ValueError("ID bit 0 must be 0: a frame starts with a LOW bit")
    levels = [1] * idle_bits
    levels += [(ident >> i) & 1 for i in range(4)]
    for b in data:
        levels += [0] + [(b >> i) & 1 for i in range(8)] + [1, 1]
    levels += [1] * idle_bits
    edges = []
    cur = None
    for i, lv in enumerate(levels):
        if lv != cur:
            edges.append(((t0 + i * bit_us) & 0xFFFFFFFF, lv))
            cur = lv
    return edges, t0 + len(levels) * bit_us


def _ect_c(x):
    table = [(243, 9.8, 122), (237, 3.83, 99), (228, 2.11, 80), (210, 1.11, 60), (180, 0.67, 40),
             (135, 0.44, 20), (82, 0.38, 0), (39, 0.47, -20), (15, 0.83, -40)]
    for base, k, off in table:
        if x >= base:
            return (x - base) * k + off
    return (x - 15) * 2.0 - 60


def _bit(data, idx, bit):
    return (data[idx] >> bit) & 1 if idx < len(data) else ""


def _val(data, idx, fn):
    return round(fn(data[idx]), 2) if idx < len(data) else ""


ECU_FIELDS = [
    "ecu_age_s", "ecu_id", "ecu_n", "ecu_inj_ms", "ecu_timing", "ecu_iac_pct", "ecu_rpm",
    "ecu_air_raw", "ecu_ect_c", "ecu_tps_pct", "ecu_spd_kmh", "ecu_corr1", "ecu_corr2",
    "ecu_closed_loop", "ecu_cold", "ecu_knock", "ecu_starter", "ecu_idle", "ecu_ac",
    "ecu_neutral", "ecu_rich1", "ecu_rich2", "ecu_raw",
]


def interpret(ident, data):
    """Frame -> dict of ECU_FIELDS (minus ecu_age_s). Unverified mapping, see module doc."""
    return {
        "ecu_id": ident,
        "ecu_n": len(data),
        "ecu_inj_ms": _val(data, 1, lambda x: x * 0.125),
        "ecu_timing": _val(data, 2, lambda x: x * 0.47 - 30),
        "ecu_iac_pct": _val(data, 3, lambda x: x * 100 / 255),
        "ecu_rpm": _val(data, 4, lambda x: x * 25),
        "ecu_air_raw": _val(data, 5, lambda x: x),
        "ecu_ect_c": _val(data, 6, _ect_c),
        "ecu_tps_pct": _val(data, 7, lambda x: x / 1.8),
        "ecu_spd_kmh": _val(data, 8, lambda x: x),
        "ecu_corr1": _val(data, 9, lambda x: x * 0.01953125),
        "ecu_corr2": _val(data, 10, lambda x: x * 0.01953125),
        "ecu_cold": _bit(data, 11, 1),
        "ecu_knock": _bit(data, 11, 4),
        "ecu_closed_loop": _bit(data, 11, 5),
        "ecu_starter": _bit(data, 12, 0),
        "ecu_idle": _bit(data, 12, 1),
        "ecu_ac": _bit(data, 12, 2),
        "ecu_neutral": _bit(data, 13, 3),
        "ecu_rich1": _bit(data, 14, 4),
        "ecu_rich2": _bit(data, 14, 5),
        "ecu_raw": " ".join("%02X" % b for b in data),
    }
