# tests/unit/logic — pure decision logic

These tests cover the code in `src/aurora_sensor_agent/logic/`: the excursion state machine, the
median filter, the backoff maths, batch splitting, and the LED/buzzer mapping. That code has **no
I/O** — it takes plain values (or an injected `Clock`) and returns plain values — so these tests run
in milliseconds with no hardware, network, or Docker.

What each file proves:

| File | Proves |
|---|---|
| `test_excursion.py` | Dwell, recovery, short-spike-no-alarm, flapping, peak tracking, and a backward-clock guard — plus a data-driven run of the shared fixture set in `tests/fixtures/excursions/`. |
| `test_filter.py` | The NaN/inf guard, the calibration offset, and that the median ignores a single outlier. |
| `test_backoff.py` | Exponential growth, the cap, jitter staying within the cap, and determinism for a seed. |
| `test_batch.py` | Splitting by count and by bytes, and a stable per-batch idempotency key. |
| `test_indicator.py` | The excursion-state → colour/buzzer mapping, over fake pins. |

The excursion machine is the centrepiece: the `cases.json` fixture set is the same contract the
server engine (milestone 10) will be held to, so the two implementations can be proved to agree.
