# ECU pinout and measurements

Fill this in from the factory wiring diagram (EWD) for the exact vehicle, then confirm every pin with a multimeter. Nothing in the "ECU pin" or "wire color" columns is trustworthy until it comes from the EWD; terminal names below are the usual Toyota ones and still need checking against the diagram.

Measure each signal **key on, engine off** and **engine idling warm**, and for VS/VTA also during a rev. If any reading can go over 5 V, it uses the divided input (docs/22re/hardware.md), and its `divider` in `pc/profiles/p22re.py` must match.

Vehicle: ______  Engine: 22R-E  EWD source: ______  Date measured: ______

| Signal | ECU terminal | ECU pin # | Wire color | Key on (V) | Idle (V) | Rev (V) | Nano pin | Input circuit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Sensor ground | E2 | | | 0 | 0 | | GND | direct |
| Airflow meter signal | VS | | | | | | A0 | direct if under 5 V |
| Throttle position | VTA | | | | | | A1 | direct if under 5 V |
| Idle contact | IDL | | | | | | A2 | divided |
| Coolant temp | THW | | | | | | A3 | direct |
| Intake air temp | THA | | | | | | A4 | direct |
| Oxygen sensor | OX | | | | | | A5 | direct |
| ECU supply | +B | | | | | | A6 | divided |
| Ignition trigger | IGT | | | | | | D3 | IGT circuit |
| Injectors group 1 | #10 | | | | | | D4 | injector circuit |
| Sensor reference (do not tap) | VC | | | | | | none | measure only |
| Diag check connector | T, E1 | | | | | | none | jumper for codes / base timing |

## Notes from measuring

- Nano 5V pin measured on USB: ______ V (put it in `pc/config.py` as `NANO_VCC`)
- Anything that didn't match the EWD:
