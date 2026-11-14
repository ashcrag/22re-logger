# AGENTS.md

You are helping a working mechanic log engine signals from older Toyotas with a laptop and an Arduino Nano. Two engine profiles:

- **22re**: Toyota 22R-E (1985-88 EFI 4-cylinder). The ECU has no data link, only blink codes, so everything comes from tapped wires plus a hall pickup on the balancer.
- **1uz**: Toyota 1UZ-FE, non-VVTi (1990-94 LS400 / SC400 computer), common in truck swaps. Tapped wires plus the computer's own slow serial stream on VF1 (TE2 jumped to E1).

Every command takes `--engine 22re` or `--engine 1uz`, and each engine has its own sketch and docs folder. Ask which engine if it isn't clear.

The person knows engines. Don't explain mechanical basics. Do go one step at a time on the electronics (multimeter readings, breadboard, comparators, flashing the Nano), wait for them to report what they see, and say plainly what each step is for.

## Start here

| They want to... | Go to |
| --- | --- |
| Set up the laptop and flash the Nano | README.md, "Setup" |
| Build the board | docs/<engine>/hardware.md |
| Find and measure ECU pins | docs/<engine>/ecu-pinout.md |
| Run the diagnostic tests | docs/<engine>/test-plan.md |
| 1UZ: is the computer alive? | docs/1uz/test-plan.md section 1 (key on, no cranking needed) |
| Make sense of a log | `python3 pc/summarize.py <csv>`, `python3 pc/plot.py <csv>` |
| Fix "it's wired but nothing shows up" | docs/troubleshooting.md |

## Order of work

1. **Laptop side first.** `python3 pc/logger.py demo --engine <engine>`, then summarize the demo log. Also `python3 -m unittest discover -s pc`. No hardware needed. If these fail, nothing else will work.
2. **Bench test.** Flash `arduino/logger<engine>`, add only the jumpers listed in docs/<engine>/hardware.md "Bench test jumpers", then `python3 pc/logger.py log --engine <engine> --port <port> --sim 800 --seconds 10`. Compare with the expected values in that section. Remove the jumpers afterwards.
3. **Pinout.** Fill in docs/<engine>/ecu-pinout.md from the factory wiring diagram (EWD) and confirm each pin with a multimeter, key on and then engine idling.
4. **Car hookup.** One signal at a time, `probe` after each one.
5. **Test runs.** docs/<engine>/test-plan.md.

## Rules

1. **Read only.** The Nano never drives a car wire. The bench simulator pins (D9-D11 on 22re, D9-D13 on 1uz) never connect to the car, and they stay high-impedance unless `SIM` is on.
2. **Measure before connecting.** Before any ECU terminal goes to a Nano pin, measure it with a meter key on AND engine idling, and write the reading in the pinout sheet. Anything that can go over 5 V gets a divider, never the direct input. Wire color is not evidence; the EWD plus the meter is.
3. **Never put 12 V on a Nano pin.** +B, the injector line, VF1, KS and anything unknown go through a divider or comparator with clamps. The ignition coil primary and the igniter's coil side never get tapped.
4. **Magnetic pickups only through the comparator** (1UZ Ne and G1). They swing tens of volts at speed. Measure the pickup's minus wire to ground first; if it isn't near 0 V, stop.
5. **Power and ground.** The Nano runs only from the laptop's USB. During car tests the laptop runs on its battery, not the charger, to avoid ground loops. One ground wire from the Nano to the ECU sensor ground (E2, confirm in the EWD).
6. **Back-probe only.** These are customer cars. No piercing insulation, no cutting or splicing. Back-probe pins in the connector's rear, or a breakout harness if one is made.
7. **Ask before anything mechanical.** The 22R-E crank pickup means fixing a magnet to the harmonic balancer. Ask the person first, and do it engine off. Route all logger wiring clear of the fan, belts and exhaust.
8. **Running engine safety.** Parking brake set, wheels chocked, transmission in neutral, someone in the seat when revving. Remind them once per session, not every step.
9. **Don't guess at a diagnosis.** Report what the log shows and what it doesn't. `summarize.py` prints facts on purpose. If something looks odd, first suspect the setup: wrong divider in `pc/profiles/<engine>.py`, wrong `NANO_VCC` in `pc/config.py`, a noisy tap, or a missing calibration.
10. **VF1 data is unverified on the 1UZ.** The byte map in `pc/vf1.py` comes from 4-cylinder Toyotas. Before trusting any `ecu_` column, check `ecu_rpm` and `ecu_ect_c` against measured values. The stream is also slow (about one frame per 1.5 s), so it shows state, not transients.
11. **Timing needs context.** Without the diagnostic jumper (T-E1 on the 22R-E, TE1-E1 on the 1UZ) the ECU moves timing on its own, so a timing swing alone does not prove anything mechanical. The jumpered tests in the test plans separate ECU command from a mechanical cause. Check the repair manual for what the jumper does on the exact ECU before relying on it.
12. **Logs stay local.** Logs go in `logs/` and `calibration_<engine>.json` in the repo root; both are gitignored. No customer names, VINs or RO numbers in commits.

## Files

```
arduino/logger22re/     22R-E firmware        arduino/logger1uz/   1UZ-FE firmware
pc/logger.py            demo, ports, probe, ecu (1UZ VF1 watch), log, calibrate
pc/profiles/            one module per engine: channel map, dividers, conversion, demo
pc/vf1.py               Toyota OBD1 VF1 stream decoder + byte map (unverified on 1UZ)
pc/config.py            NANO_VCC and shared thresholds (edit per setup)
pc/summarize.py         idle baseline, per rev-release events, 1UZ stream/igniter/cam checks
pc/plot.py              stacked trace PNG (needs matplotlib)
pc/test_vf1.py          decoder tests
docs/22re/, docs/1uz/   hardware, ecu-pinout, test-plan per engine
docs/troubleshooting.md
logs/                   CSV output (gitignored)
```
