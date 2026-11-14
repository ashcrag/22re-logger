# toyota-tap-logger

A passive engine signal logger for older Toyotas. An Arduino Nano taps the ECU connector, timestamps the ignition, injector and crank signals, samples the sensor voltages, and streams it all to a laptop as CSV. On computers that have it, it also decodes the ECU's own OBD1 diagnostic stream.

| Engine | Profile | What it reads |
| --- | --- | --- |
| Toyota 22R-E (1985-88 EFI) | `22re` | tapped wires only (the ECU has no data link) plus a hall pickup on the balancer |
| Toyota 1UZ-FE non-VVTi (1990-94 LS400 / SC400 computer) | `1uz` | tapped wires, the factory crank/cam pickups, and the VF1 serial stream |

Inspired by [xj-scanner](https://github.com/MZULALI/xj-scanner), which does agent-guided logging on a 1994 Jeep. The VF1 bit format follows the community decoders by talofer99 / GadgetFreak and [hyperion11/toyota-obd-1](https://github.com/hyperion11/toyota-obd-1).

**Status:** untested on a car. The laptop side runs end to end on synthetic demo data for both engines, and the VF1 decoder has unit tests. Neither firmware sketch has been compiled or run on a Nano yet.

## What it computes

rpm, ignition dwell, injector pulse width, and ignition timing measured against the crankshaft (22R-E: hall pickup on the balancer; 1UZ: the factory 12-tooth Ne pickup plus G1). On the 1UZ also airflow meter frequency, both igniters, cam-to-crank phase, and the computer's own view from VF1: closed loop, idle, neutral, A/C and knock flags, commanded timing, idle valve, coolant temp, speed.

## Setup

Laptop (Kali or macOS):

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r pc/requirements.txt      # pyserial
pip install matplotlib                  # optional, for plots
python3 pc/logger.py demo --engine 1uz  # proves the laptop side (or --engine 22re)
python3 pc/summarize.py logs/demo_1uz_*.csv
python3 -m unittest discover -s pc
```

Firmware, with [arduino-cli](https://arduino.github.io/arduino-cli/). Pick the sketch for the engine:

```sh
arduino-cli core install arduino:avr
arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328old arduino/logger1uz     # or logger22re
arduino-cli upload  --fqbn arduino:avr:nano:cpu=atmega328old -p <port> arduino/logger1uz
```

Most clone Nanos (CH340 USB chip) want `cpu=atmega328old`. If upload times out, try `cpu=atmega328`. Ports: `python3 pc/logger.py ports` (Linux `/dev/ttyUSB0`, macOS `/dev/cu.wchusbserial*`). On Kali, add yourself to the `dialout` group if the port is permission denied.

Then follow AGENTS.md "Order of work": demo, bench test, pinout, car.

## Safety

Read AGENTS.md "Rules" before connecting anything to a car. Short version: read only, measure every pin before it goes in, nothing over 5 V without a divider or comparator, laptop on battery, back-probe only.

## License

Not chosen yet.
