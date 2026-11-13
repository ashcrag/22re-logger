# Hardware

## Shopping list

| Part | Qty | Notes |
| --- | --- | --- |
| Arduino Nano clone (ATmega328P, CH340) | 2 | One spare. Get it with headers soldered, or plan to solder them. Match the USB connector to your cable (mini-USB or USB-C). |
| Nano screw-terminal breakout board | 1 | Holds up in a car far better than a breadboard. |
| Resistor assortment (1/4 W) | 1 kit | Needs 10k, 47k, 15k, 22k, 100k, 2.2k. |
| 5.1 V zener diodes (1N4733A) | 10 | Over-voltage clamps on every input. |
| 100 nF ceramic capacitors | 10 | Analog input filtering. |
| Back-probe pin kit | 1 | For tapping the ECU connector without damage. |
| Hall sensor, A3144 or a 3-wire NPN hall module | 2 | Crank pickup. |
| Small neodymium magnet, about 6 x 3 mm | 2 | Fixed to the harmonic balancer. |
| High-temp epoxy (JB Weld or similar) | 1 | For the magnet. |
| Hookup wire, heat shrink, zip ties | | Keep runs short and away from plug wires. |

A cheap digital multimeter is required; you'll measure every pin before it goes on the board.

## Input circuits

Every input gets a series resistor and a 5.1 V zener on the Nano side, so a wrong guess clamps instead of killing the Nano or loading the ECU.

### Direct analog (signal never above 5 V): VS, VTA, THW, THA, OX

```
ECU pin ----[10k]----+---- Nano A0..A7
                     |
                  [100nF]  [5.1V zener, band to the Nano pin]
                     |         |
GND -----------------+---------+
```

The 10k plus 100 nF filters noise and feeds the ADC's sample cap, so the ECU line sees almost no load. Only use this circuit after the meter shows the signal stays under 5 V at key on AND at idle and during a rev.

### Divided analog (up to about 20 V): IDL, +B, anything unknown

```
ECU pin ----[47k]----+---- Nano pin
                     |
                  [15k]  [100nF]  [5.1V zener]
                     |      |        |
GND -----------------+------+--------+
```

Divider ratio 4.133 (already set in `pc/config.py`). 15 V in reads 3.63 V at the pin.

### IGT (ECU to igniter): D3

```
IGT ----[10k]----+---- Nano D3
                 |
             [100k]  [5.1V zener]
                 |       |
GND -------------+-------+
```

The 100k keeps the pin from floating when nothing's connected. Tap IGT at the ECU side only, never the coil side of the igniter.

### Injector (#10 group, low side): D4

```
Injector -(ECU #10)----[47k]----+---- Nano D4
                                |
                            [22k]  [5.1V zener]
                                |       |
GND ----------------------------+-------+
```

The ECU grounds the injector to open it, so the line sits near battery voltage when closed and near 0 V when open. When it closes, the injector coil kicks the line far above battery voltage for a moment; the 47k and the zener absorb that. 12 V reads about 3.8 V at the pin (logic high), 0 V reads low.

### Crank pickup: D2

```
Nano 5V ----+--------------- hall VCC
            |
          [2.2k]
            |
Nano D2 ----+--------------- hall OUT
Nano GND ------------------- hall GND
```

The hall sensor pulls D2 low when the magnet passes. One magnet means one pulse per crank revolution.

**Mounting (ask before doing this on a customer car):** epoxy the magnet to the balancer face near its rim, and mount the sensor on a small bracket 2-5 mm away, engine off. The magnet doesn't need to be at TDC; `calibrate` measures the offset. Keep the sensor wire away from plug wires and belts. A gram of magnet doesn't upset the balancer, but the epoxy must be fully cured before the engine runs.

## Ground

One wire from Nano GND to the ECU sensor ground (E2, confirm in the EWD). Laptop on battery during tests.

## Bench test jumpers

For `--sim` only, with nothing else connected: D9 to D2, D10 to D3, D11 to D4. The simulator puts out an active-low crank pulse at 0 deg, IGT dwell 3 ms falling at 170 and 350 deg, and a 2.5 ms injector pulse at 90 deg. In the log, `spark_angle_raw` should read about 170 and rpm should match the `--sim` value.
