# 1UZ-FE hardware

Same Nano, screw-terminal board, resistors, zeners and capacitors as the 22R-E build (docs/22re/hardware.md has the shopping list). The 1UZ adds:

| Part | Qty | Why |
| --- | --- | --- |
| LM393 dual comparator (DIP-8) | 2 | Turns the magnetic Ne and G1 pickups and the VF1 data line into clean logic edges. One chip does two channels. |
| Schottky diodes, BAT85 or 1N5817 | 6 | Negative clamp on each comparator input. The LM393 misbehaves if an input goes more than 0.3 V below ground; a 1N4148 lets it reach 0.6 V. |
| 1N4148 diodes | 6 | Positive clamp to 5 V on each comparator input. |
| 4.7M and 1M resistors | a few | Comparator hysteresis. Not in the 100-value kit; buy separately or use the kit's largest values. |

No magnet or hall sensor: the 1UZ already has a 12-tooth crank pickup (Ne).

## Pin map

| Nano | Signal | Circuit |
| --- | --- | --- |
| D2 | Ne+ crank pickup | magnetic pickup comparator |
| D7 | G1+ cam pickup | magnetic pickup comparator |
| D8 | VF1 data (TDCL) | data line comparator |
| D3 | IGT1 | IGT circuit (as 22R-E) |
| D4 | IGT2 | IGT circuit (as 22R-E) |
| D5 | one injector group (#10, #20, #30 or #40) | injector circuit (as 22R-E) |
| D6 | KS airflow meter | divided digital, see below |
| A0 | VTA | direct |
| A1 | IDL | divided |
| A2 | THW | direct |
| A3 | THA | direct |
| A4 | OX1 main O2, bank 1 | direct |
| A5 | OX2 main O2, bank 2 | direct |
| A6 | +B | divided |
| A7 | VF1 level (same wire as D8) | divided |
| GND | ECU sensor ground (E2) | |

Check every terminal against the EWD for the exact computer; this table is the plan, not the pinout.

## Magnetic pickup comparator (Ne on D2, G1 on D7)

The pickup makes an AC voltage: a fraction of a volt while cranking, tens of volts at high rpm. The ECU reads it already; the logger only listens through 100k.

```
Pickup + (at ECU) ---[100k]---+--------------+-------- LM393 IN+
                              |              |
                       Schottky (to GND,  1N4148 (to +5V,
                       band toward IN+)    band toward +5V)

+5V ---[100k]---+--- LM393 IN-     threshold about +0.15 V
                |
              [3.3k]
                |
GND ------------+

LM393 OUT ---+--- Nano D2 (or D7)
             |
          [10k] to +5V (pull-up; open collector output)

LM393 OUT ---[4.7M]--- IN+   (hysteresis, about 0.1 V)
LM393 VCC = Nano 5V, GND = Nano GND
```

Wire it so a passing tooth pulls the output LOW; the firmware counts falling edges. If probe shows edges at the wrong rate (double, or none until high rpm), swap IN+ and IN- roles or adjust the threshold resistor.

**Before connecting:** measure the pickup's minus wire (Ne-, G-) to ground, key on. It should be near 0 V. If the ECU biases it to some other voltage, stop: the threshold above assumes a ground-referenced pickup.

## VF1 data comparator (D8)

VF1 may swing 0-5 V or 0-12 V depending on the computer; the comparator doesn't care.

```
VF1 ---[100k]---+---------+---- LM393 IN+
                |         |
             Schottky   1N4148 (to +5V)
              (to GND)

+5V ---[100k]---+--- IN-   threshold about 2.5 V
                |
             [100k]
                |
GND ------------+

OUT ---[10k] to +5V, and to Nano D8.   OUT ---[1M]--- IN+ (hysteresis)
```

Also run VF1 through the 47k/15k divider to A7 so probe shows its actual voltage swing. If VF1's high level drops when that divider is connected (a weak pull-up inside the computer), take the A7 tap off; the comparator alone loads it by only 100k.

## KS airflow meter (D6)

The optical Karman-vortex meter's KS line is a pulse train whose frequency rises with airflow. Measure its high level first (key on, engine idling).
- 5 V or less: 10k series + 5.1 V zener, like an analog direct input but to D6.
- Higher: the injector circuit's 47k/22k divider + zener.

## Bench test jumpers

For `--sim` only, with nothing else connected:

| Sim output | Jumper to | Simulates |
| --- | --- | --- |
| D9 | D2 | Ne, 12 teeth/rev |
| D10 | D7 | G1, once per 2 revs, half a tooth after a Ne tooth |
| D11 | D3 | IGT1, 3 ms dwell, sparks at 170/350/530/710 deg |
| D12 | D5 | injector group, 2.5 ms once per 2 revs |
| D13 | D6 | KS at 100 Hz |

Expect rpm equal to the `--sim` value, `spark_angle_raw` about 170, `g1_phase_deg` about 15, injector 2.5 ms, airflow 100 Hz, and `ig2_ok` 0 (IGT2 isn't simulated).
