"""VF1 decoder tests: python3 -m unittest discover -s pc"""

import random
import unittest

import vf1


def run(edges, invert=False):
    d = vf1.VF1Decoder(invert=invert)
    out = [f for f in (d.edge(t, lv) for t, lv in edges) if f]
    return out, d


class VF1Tests(unittest.TestCase):
    def frames(self, n, rnd, t0=0, jitter=0, invert=False):
        edges, want, t, level = [], [], t0, None
        for _ in range(n):
            ident = rnd.randrange(8) * 2  # bit 0 is always 0 on the wire
            data = [rnd.randrange(256) for _ in range(rnd.randrange(10, 24))]
            want.append((ident, data))
            fe, t_end = vf1.encode(ident, data, t0=t)
            for te, lv in fe:
                if lv != level:
                    jt = (te + rnd.randint(-jitter, jitter)) & 0xFFFFFFFF
                    edges.append((jt, (1 - lv) if invert else lv))
                    level = lv
            t = t_end
        # a frame completes when the next one's start edge ends the idle
        edges.append((t & 0xFFFFFFFF, 1 if invert else 0))
        return edges, want

    def test_round_trip(self):
        edges, want = self.frames(20, random.Random(1))
        got, d = run(edges)
        self.assertEqual(got, want)
        self.assertEqual(d.fails, 0)

    def test_jitter(self):
        # +-1.5 ms of edge jitter on 8 ms bits still decodes
        edges, want = self.frames(20, random.Random(2), jitter=1500)
        got, _ = run(edges)
        self.assertEqual(got, want)

    def test_counter_wrap(self):
        edges, want = self.frames(5, random.Random(3), t0=0xFFFFFFFF - 3_000_000)
        got, _ = run(edges)
        self.assertEqual(got, want)

    def test_inverted_line(self):
        edges, want = self.frames(5, random.Random(4), invert=True)
        got, _ = run(edges, invert=True)
        self.assertEqual(got, want)
        wrong, _ = run(edges, invert=False)
        self.assertNotEqual(wrong, want)

    def test_interpret_known_bytes(self):
        e = vf1.interpret(0, [0, 20, 85, 77, 32, 0, 230, 36, 0, 128, 128, 0x20, 0x02, 0x08, 0x10])
        self.assertEqual(e["ecu_rpm"], 800)
        self.assertAlmostEqual(e["ecu_inj_ms"], 2.5)
        self.assertAlmostEqual(e["ecu_timing"], 9.95, places=2)
        self.assertEqual((e["ecu_closed_loop"], e["ecu_idle"], e["ecu_neutral"], e["ecu_rich1"]), (1, 1, 1, 1))


if __name__ == "__main__":
    unittest.main()
