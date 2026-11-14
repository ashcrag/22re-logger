"""Per-setup settings shared by every engine profile.

Channel maps and dividers live in pc/profiles/<engine>.py; edit those
after measuring (docs/<engine>/ecu-pinout.md).
"""

# Voltage at the Nano's 5V pin while it runs on the laptop's USB.
# Measure it once with a multimeter. Clone Nanos often sit around 4.6-4.9 V,
# and every analog reading scales with this number.
NANO_VCC = 5.00

# IDL contact reads near 0 V when the throttle is closed. Verify on the car.
IDL_CLOSED_BELOW_V = 1.0

# O2 sensor switch point used for lean/rich percentages in summaries.
OX_SWITCH_V = 0.45

# 47k over 15k input divider: signal volts = pin volts * this
DIV_47_15 = (47 + 15) / 15
