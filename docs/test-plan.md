# Test plan: idle stumbles after a held rev

The complaint this was built for: the engine idles, but after holding a rev for a few seconds and letting off, it struggles to idle and takes a while to smooth out. Better when warm. Each run below answers one question. Name each log with `--name` and drop markers (type a word, Enter) at every rev and release.

Before any run: blink codes read and written down (T-E1 jumper at the check connector, key on, engine off; read code meanings from the repair manual), engine fully warm unless the run says cold, laptop on battery.

## Run 1: warm idle baseline

`log --name warm-idle --seconds 120`. Hands off.

Tells you what "normal" looks like on this car: idle rpm wander, O2 switching, injector time, VS at idle, +B. Every later run is compared to this.

## Run 2: rev, hold, release

`log --name rev-release`. Do five events, about 20 s of idle between each: hold 3000 rpm for 3 s, 5 s, 10 s, 10 s, 3 s. Marker at each rev and each release.

Then `summarize.py`. Look at how each event's stumble scales with hold time, and which signal moves first after release:

| What the log shows after release | Points toward (not a diagnosis) |
| --- | --- |
| O2 pinned lean, injector time normal or low, VS normal | air getting in that the airflow meter didn't measure, or not enough fuel delivered for the injector time |
| O2 pinned lean, VS reading low for the rpm | airflow meter or its signal |
| O2 rich, injector time high | fuel side: injector, pressure regulator, or ECU commanding rich |
| IDL stays open after release | throttle stop / switch adjustment |
| Timing moves a lot, everything else steady | ignition side; run 3 decides whether ECU or mechanical |
| +B dips hard | charging or a big electrical load at idle |
| Everything steady but rpm still sags | something not on this logger: vacuum, EGR, mechanical |

## Run 3: same, with T-E1 jumped (the chain test)

Needs the crank pickup and a calibration. Check the repair manual for what the T-E1 jumper does with the engine running on this ECU; on these engines it's the base-timing check condition, which should hold timing fixed while the idle contact is closed.

1. Engine warm, T-E1 jumped, timing light on #1. Read the timing light.
2. `calibrate --light <reading>`. Note the spread it reports.
3. `log --name rev-release-te1` and repeat the run 2 pattern.

With the ECU holding timing fixed, any timing swing after release (once IDL closes again) is mechanical: crank-to-distributor phase moving, which on a 22R-E means the timing chain and its tensioner. If timing stays put to within about a degree while the stumble still happens, the chain is not the cause of the stumble.

## Run 4: cold start (optional)

From an overnight sit, logger connected before starting. `log --name cold-start` from key on through warm-up, with a rev-release every couple of minutes. Shows how the stumble changes with coolant temp (THW volts climb or drop as it warms; read the curve from the repair manual).

## After the runs

Keep the CSVs and PNGs (`plot.py`) with the job notes. Copy the summary numbers into the RO notes as plain facts.
