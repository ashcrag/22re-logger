"""Setup configuration. Edit after measuring (see docs/ecu-pinout.md).

Everything here is per-setup: which ECU signal lands on which Nano pin,
and how much each one is divided down before it reaches the pin.
"""

# Voltage at the Nano's 5V pin while it runs on the laptop's USB.
# Measure it once with a multimeter. Clone Nanos often sit around 4.6-4.9 V,
# and every analog reading scales with this number.
NANO_VCC = 5.00

# Analog channels, in Nano pin order A0..A7.
#   key       short column name in the CSV
#   label     what it is on the car
#   divider   signal volts / pin volts. 1.0 = direct (10k series only).
#             47k over 15k = (47 + 15) / 15 = 4.133
DIV_47_15 = (47 + 15) / 15

CHANNELS = [
    # key     label                              divider
    ("vs",    "VS airflow meter signal",          1.0),
    ("vta",   "VTA throttle position",            1.0),
    ("idl",   "IDL throttle idle contact",        DIV_47_15),
    ("thw",   "THW coolant temp sensor",          1.0),
    ("tha",   "THA intake air temp sensor",       1.0),
    ("ox",    "OX oxygen sensor",                 1.0),
    ("batt",  "+B ECU supply",                    DIV_47_15),
    ("spare", "spare (A7)",                       1.0),
]

# IDL contact reads near 0 V when the throttle is closed. Verify on the car.
IDL_CLOSED_BELOW_V = 1.0

# O2 sensor switch point used for lean/rich percentages in summaries.
OX_SWITCH_V = 0.45

# 22R-E: 4 cylinders, so 2 IGT pulses per crank revolution.
IGT_PER_REV = 2

# Where calibration (crank pickup offset) is stored. Per car, not committed.
CALIBRATION_FILE = "calibration.json"
