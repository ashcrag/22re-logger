"""Engine profiles. Each module defines the same small interface:

  NAME, TITLE          short id and human name
  RAW_FIELDS           firmware frame fields (the firmware's H line overrides)
  CHANNELS             analog inputs A0..A7 as (key, label, divider)
  EXTRA_FIELDS         CSV columns after decode.COMMON_FIELDS
  PROBE_NAMES          digital pin -> what's wired there
  HAS_VF1              firmware also streams VF1 edges (E lines)
  ANGLE_SPAN           firing interval of the timed IGT line, degrees
  BASE_TIMING_NOTE     what the timing light should read for calibration
  convert(raw, cal, t0_ms) -> CSV row dict
  spark_angle(raw, edge) -> degrees in [0, ANGLE_SPAN) or None
  demo_lines(seconds)  synthetic firmware output lines
"""

import importlib

ENGINES = {"22re": "p22re", "1uz": "p1uz"}


def get(name):
    if name not in ENGINES:
        raise SystemExit("unknown engine %r; choose one of: %s" % (name, ", ".join(ENGINES)))
    return importlib.import_module("profiles." + ENGINES[name])
