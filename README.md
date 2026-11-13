# 22re-logger

A passive signal logger for the Toyota 22R-E. An Arduino Nano taps the ECU connector, timestamps the ignition, injector and crank signals, samples the sensor voltages, and streams it all to a laptop as CSV. Built for the idle problems the ECU's blink codes can't explain.

Inspired by [xj-scanner](https://github.com/MZULALI/xj-scanner), which does the same kind of agent-guided work on a 1994 Jeep. The difference: a 22R-E ECU has no serial data link, so instead of asking the ECU, this listens to its wires.

**Status:** untested on a car. The laptop side runs end to end on synthetic demo data. The firmware has not been compiled or run on a Nano yet.

## What it logs

| Signal | Nano pin | How |
| --- | --- | --- |
| VS airflow meter | A0 | analog |
| VTA throttle position | A1 | analog |
| IDL idle contact | A2 | analog, divided |
| THW coolant temp | A3 | analog |
| THA intake air temp | A4 | analog |
| OX oxygen sensor | A5 | analog |
| +B ECU supply | A6 | analog, divided |
| spare | A7 | analog |
| Crank pickup (hall + magnet on balancer) | D2 | interrupt timestamp |
| IGT (ECU to igniter) | D3 | interrupt timestamp |
| Injector #10 group | D4 | interrupt timestamp |

From those it computes rpm, dwell, injector pulse width, and ignition timing measured against the crankshaft. The 22R-E distributor is driven by the camshaft, so if the timing chain goes slack, spark moves relative to the crank; the crank pickup is what lets the logger see that.

## Setup

Laptop (Kali or macOS):

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r pc/requirements.txt      # pyserial
pip install matplotlib                  # optional, for plots
python3 pc/logger.py demo               # proves the laptop side
python3 pc/summarize.py logs/demo_*.csv
```

Firmware, with [arduino-cli](https://arduino.github.io/arduino-cli/):

```sh
arduino-cli core install arduino:avr
arduino-cli compile --fqbn arduino:avr:nano:cpu=atmega328old arduino/logger22re
arduino-cli upload  --fqbn arduino:avr:nano:cpu=atmega328old -p <port> arduino/logger22re
```

Most clone Nanos (CH340 USB chip) want `cpu=atmega328old`. If upload times out, try `cpu=atmega328`. Ports: `python3 pc/logger.py ports` (Linux `/dev/ttyUSB0`, macOS `/dev/cu.wchusbserial*`). On Kali, add yourself to the `dialout` group if the port is permission denied.

Then follow AGENTS.md "Order of work": demo, bench test, pinout, car.

## Safety

Read AGENTS.md "Rules" before connecting anything to a car. Short version: read only, measure every pin before it goes in, nothing over 5 V without a divider, laptop on battery, back-probe only.

## License

Not chosen yet.
