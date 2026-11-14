# 1UZ-FE pinout and measurements

Fill this in from the EWD for the exact computer in the truck (1990-94 LS400 or 1992-94 SC400 non-VVTi; anything else needs a different profile). Swaps often cut the LS400 body harness, including the TDCL, so VF1 and TE2 may only exist at the ECU connector. Terminal names are Toyota's usual ones and still need checking against the diagram.

Measure each signal **key on, engine off** and **engine idling warm**; for VTA and KS also during a rev. Anything that can go over 5 V uses a divided input.

Vehicle: ______  Computer part number: ______  EWD source: ______  Date: ______

| Signal | ECU terminal | ECU pin # | Wire color | Key on (V) | Idle (V) | Rev (V) | Nano | Circuit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Sensor ground | E2 | | | 0 | 0 | | GND | direct |
| Crank pickup + | NE+ (NE) | | | | AC | AC | D2 | pickup comparator |
| Crank pickup - | NE- | | | must be ~0 | | | none | measure only |
| Cam pickup + | G1+ (G1) | | | | AC | AC | D7 | pickup comparator |
| Cam pickup - | G- | | | must be ~0 | | | none | measure only |
| Igniter 1 | IGT1 | | | | | | D3 | IGT circuit |
| Igniter 2 | IGT2 | | | | | | D4 | IGT circuit |
| Injector group | #10 (or #20/#30/#40) | | | | | | D5 | injector circuit |
| Airflow meter | KS | | | | | | D6 | see hardware.md |
| Throttle position | VTA | | | | | | A0 | direct if under 5 V |
| Idle contact | IDL | | | | | | A1 | divided |
| Coolant temp | THW | | | | | | A2 | direct |
| Intake air temp | THA | | | | | | A3 | direct |
| Main O2 bank 1 | OX1 | | | | | | A4 | direct |
| Main O2 bank 2 | OX2 | | | | | | A5 | direct |
| ECU supply | +B | | | | | | A6 | divided |
| Diag data out | VF1 | | | | | | D8 + A7 | VF1 comparator + divided |
| Diag test mode | TE2 | | | | | | none | jumper to E1 for VF1 data |
| Diag codes / base timing | TE1 | | | | | | none | jumper to E1 for blink codes and base timing |

Bank naming: owners on ClubLexus report the manual's figures disagree on which bank is OX1. Confirm on the car (unplug one sensor, see which channel goes flat) before writing conclusions about a bank.

## Notes from measuring

- Nano 5V pin measured on USB: ______ V (put it in `pc/config.py` as `NANO_VCC`)
- VF1 swing (A7 during `logger.py ecu`): low ____ V, high ____ V; idles: HIGH / LOW (LOW means use `--invert`)
- Anything that didn't match the EWD:
