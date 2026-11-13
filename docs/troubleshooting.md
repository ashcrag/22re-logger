# Troubleshooting

Work from the laptop outwards.

| Symptom | Check |
| --- | --- |
| `demo` fails | Python too old (needs 3.8+) or running from the wrong folder. Run from the repo root as `python3 pc/logger.py demo`. |
| `pyserial is missing` | Activate the venv, `pip install -r pc/requirements.txt`. |
| No serial port listed | USB cable is charge-only (very common), or the CH340 driver. Linux has it built in; current macOS does too. |
| Permission denied on `/dev/ttyUSB0` | Kali: `sudo usermod -aG dialout $USER`, then log out and back in. |
| Upload times out | Try `cpu=atmega328` instead of `cpu=atmega328old` (or the reverse). |
| `No 22RE-LOGGER answered` | Wrong port, firmware not flashed, or another program (Arduino IDE serial monitor) holds the port. |
| Bench `--sim` shows rpm 0 | Jumpers D9-D2 / D10-D3 / D11-D4 not seated, or `SIM` rpm outside 300-6000. |
| An analog channel reads exactly 0 | Tap not making contact, or missing ground wire. Check with `probe`. |
| An analog channel pins near the top | Signal is over 5 V at the pin. Disconnect, measure, switch to the divided input and update `pc/config.py`. |
| All analog readings a few % off a meter | `NANO_VCC` in `pc/config.py` doesn't match the measured 5V pin. |
| Crank edges/s jumpy or double | Sensor too far from the magnet, or wire next to plug wires. 2-5 mm gap, re-route. |
| IGT edges but no timing | Crank pickup missing; timing needs both. |
| Timing spread over 1.5 deg at steady idle | Noisy crank pickup, or the idle itself is unsteady. Calibrate again at a steadier idle with T-E1 jumped. |
| Injector edges/s far above rpm/60 | Flyback ringing getting through. Check the zener, and that you're on the injector side the ECU switches. |
