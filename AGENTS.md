# AGENTS.md

You are helping a working mechanic log engine signals from a Toyota 22R-E (1985-88 era EFI) with a laptop and an Arduino Nano. The ECU on these engines has no data link: it only flashes blink codes. So this tool taps the wires at the ECU connector and records what the sensors and the ECU are actually doing.

The person knows engines. Don't explain mechanical basics. Do go one step at a time on the electronics (multimeter readings, breadboard, flashing the Nano), wait for them to report what they see, and say plainly what each step is for.

## Start here

| They want to... | Go to |
| --- | --- |
| Set up the laptop and flash the Nano | README.md, "Setup" |
| Build the board | docs/hardware.md |
| Prove it works before touching the car | "Order of work" below, steps 1 and 2 |
| Find and measure ECU pins | docs/ecu-pinout.md |
| Run the diagnostic tests | docs/test-plan.md |
| Make sense of a log | `python3 pc/summarize.py <csv>`, `python3 pc/plot.py <csv>` |
| Fix "it's wired but nothing shows up" | docs/troubleshooting.md |

## Order of work

1. **Laptop side first.** `python3 pc/logger.py demo`, then summarize the demo log. No hardware needed. If this fails, nothing else will work.
2. **Bench test.** Flash the Nano, jumper D9 to D2, D10 to D3, D11 to D4 (and nothing else), then `python3 pc/logger.py log --port <port> --sim 800 --seconds 10`. Expect about 800 rpm, injector about 2.5 ms, dwell about 3 ms. Remove the jumpers afterwards.
3. **Pinout.** Fill in docs/ecu-pinout.md from the factory wiring diagram (EWD) and confirm each pin with a multimeter, key on and then engine idling.
4. **Car hookup.** One signal at a time, `probe` after each one.
5. **Test runs.** docs/test-plan.md.

## Rules

1. **Read only.** The Nano never drives a car wire. D9, D10 and D11 are bench simulator outputs; nothing from the car ever connects to them, and they stay high-impedance unless `SIM` is on.
2. **Measure before connecting.** Before any ECU terminal goes to a Nano pin, measure it with a meter key on AND engine idling, and write the reading in docs/ecu-pinout.md. Anything that can go over 5 V gets the 47k/15k divider, never the direct input. Wire color is not evidence; the EWD plus the meter is.
3. **Never put 12 V on a Nano pin.** +B, BATT, the injector line, and anything unknown go through a divider with the 5.1 V zener. The ignition coil primary and the igniter's coil side never get tapped at all.
4. **Power and ground.** The Nano runs only from the laptop's USB. During car tests the laptop runs on its battery, not the charger, to avoid ground loops. One ground wire from the Nano to the ECU sensor ground (E2, confirm in the EWD).
5. **Back-probe only.** This is a customer car. No piercing insulation, no cutting or splicing. Back-probe pins in the connector's rear, or a breakout harness if one is made.
6. **Ask before anything mechanical.** The crank pickup means fixing a magnet to the harmonic balancer and mounting a sensor near it. Ask the person before planning that, and do it engine off. Route all logger wiring clear of the fan, belts and exhaust.
7. **Running engine safety.** Parking brake set, wheels chocked, transmission in neutral, someone in the seat when revving. Remind them once per session, not every step.
8. **Don't guess at a diagnosis.** Report what the log shows and what it doesn't. `summarize.py` prints facts on purpose. If something looks odd, first suspect the setup: wrong divider in `pc/config.py`, wrong `NANO_VCC`, a noisy tap, or a missing calibration.
9. **Timing needs context.** Without the T-E1 jumper, the ECU moves timing on its own after a rev, so a timing swing alone does not prove anything mechanical. The jumpered test in docs/test-plan.md separates ECU command from chain slack. Check the repair manual for what the jumper does on this exact ECU before relying on it.
10. **Logs stay local.** Logs go in `logs/` and `calibration.json` in the repo root; both are gitignored. No customer names, VINs or RO numbers in commits.

## Files

```
arduino/logger22re/   Nano firmware (arduino-cli, arduino:avr core)
pc/logger.py          demo, ports, probe, log, calibrate
pc/config.py          channel map, dividers, NANO_VCC (edit per setup)
pc/decode.py          frame parsing and unit conversion
pc/summarize.py       idle baseline + per rev-release event report
pc/plot.py            stacked trace PNG (needs matplotlib)
docs/                 hardware, ecu-pinout, test-plan, troubleshooting
logs/                 CSV output (gitignored)
```
