# 1UZ-FE swap test plan

Built for 1UZ swaps into trucks running the original LS400/SC400 computer. Run the sections that apply; section 1 needs no engine running at all.

## 1. Is the computer alive? (key on, engine off)

Use this first after anything electrical went wrong, like a bad jump start. Needs only the ground wire, the VF1 tap and the TE2/TE1 jumpers.

1. Key on. Check engine light should come on (bulb check). If it doesn't, check the computer's power and ground feeds before anything else.
2. **Blink codes:** jump TE1 to E1. Count the flashes and look up the meanings in the repair manual. Remove the jumper.
3. **Data stream:** jump TE2 to E1, then `python3 pc/logger.py ecu --port <port>`. A live computer sends a frame about every 1.5 s. If the output shows edges but no frames, rerun with `--invert`. With the engine off, expect rpm 0, a sensible coolant temp, and throttle % that follows the pedal.

What it tells you:
- Frames arrive and values move with the pedal: the computer is alive and reading its sensors.
- No edges at all with TE2 jumped: the computer isn't talking. Its power/ground, a missing TDCL wire in the swap harness, or a damaged computer.
- Blink codes but no stream: the stream may not exist on this computer, or VF1 isn't wired. Check the EWD.

None of this checks the starter circuit. A no-crank is the chassis side: battery cables, fusible links and main fuses, starter relay, and the clutch or neutral start switch wired into the swap.

## 2. Swap health check (engine running, warm)

`log --engine 1uz --name health` with TE2 jumped, about 3 minutes, using markers. Then `summarize.py`.

| Do this | Expect in the log |
| --- | --- |
| Warm idle, hands off | `ecu_closed_loop` = 1 most of the time, both O2 channels switching, `ecu_idle` = 1 |
| Clutch in / out, or shifter to neutral and back (manual swaps) | `ecu_neutral` follows it. If it never changes, the computer doesn't see the neutral/clutch signal |
| A/C on and off (if wired) | `ecu_ac` follows, idle step `ecu_iac_pct` rises |
| Crack the throttle | `ecu_idle` drops to 0, `ecu_tps_pct` rises, VTA volts rise |
| Short drive | `ecu_spd_kmh` follows the speedo. If it stays 0, the computer has no speed signal (the A341E auto trans supplied it on the LS400) |

Also check `ecu_rpm` against the logger's own rpm and `ecu_ect_c` against a known temperature. If they disagree, the byte map in pc/vf1.py is off for this computer; fix the map before trusting the other ecu_ columns.

## 3. Base timing and cam belt

Needs Ne, G1 and IGT1 tapped.

1. Warm idle, TE1 jumped to E1, throttle closed. Toyota's spec is 10° BTDC.
2. Read the timing light, then `calibrate --engine 1uz --light <reading>`.
3. Note `g1_phase_deg` at idle. It measures where the cam pulse lands between crank teeth. A belt off by a tooth shifts it. It repeats every 30°, so compare against a known-good 1UZ rather than a fixed number, and confirm a suspected jump with the timing marks.

## 4. Drivability logging

Same rev-hold-release routine as docs/22re/test-plan.md Run 2, with markers. `summarize.py` reports the stumble, timing, injector, both O2s and airflow (KS Hz) per event. Two 1UZ extras: `ig2_ok` flags rows where one igniter stops firing, and the VF1 columns show what the computer thought, delayed by up to a frame (about 1.5 s).
