# 3. The excursion state machine is pure and driven by an injected clock

- Status: accepted
- Date: 2026-09-27

## Context

The device's most important job is to decide whether a temperature reading is a real cold-chain
breach. The rule is not "temperature is out of range" — a nurse opening the fridge door warms it for a
minute, and that must **not** alarm. The rule is: out of range continuously for longer than
`dwell_minutes` raises an excursion, and it clears only after the temperature is back in range for
`recovery_minutes`.

That is a state machine with timing, and timing is where this kind of code usually goes wrong:

- If it reads the real wall clock, a seven-day soak test takes seven real days, and a "wait 15
  minutes" test either sleeps for real or is skipped.
- If it uses the wall clock and the device's RTC is stepped by NTP, a timer can jump or go backwards.
- If the server re-derives excursions from the stored series (it must, see milestone 10), it has to
  compute the *same* answer the device did — which is only possible if the rule depends solely on the
  data, not on when the code happened to run.

## Decision

**The excursion machine is pure.** `ExcursionDetector.update(temperature, at)` takes the reading and
its timestamp and returns an event or nothing. It never reads a clock. All timing comes from the
`at` timestamps the caller passes in.

Four states: `NORMAL → PENDING` (out of range, dwell not yet elapsed) `→ EXCURSION` (raised)
`→ CLEARING` (back in range, recovery not yet elapsed) `→ NORMAL`. An in-range sample while `PENDING`
returns to `NORMAL` with no alarm (the door-opening case); an out-of-range sample while `CLEARING`
returns to `EXCURSION` (no flapping).

Two consequences of "driven by timestamps" are handled explicitly:

- **Backward clock step:** if a sample's timestamp is before the previous one, the machine freezes its
  timeline at the last timestamp, so no timer can measure negative time and no spurious event fires.
- **Shared fixtures:** `detect_excursions(series, policy)` runs the machine over a whole series. The
  fixture set in `tests/fixtures/excursions/cases.json` is the contract; the server engine (milestone
  10) will run the same fixtures, so device and server are proved to agree rather than assumed to.

The agent feeds the machine the **median-filtered** temperature, not the raw one, so a single
outlier sample cannot raise or clear an excursion.

Device-local clock-step detection (wall clock vs monotonic divergence per cycle) lives in the agent,
not the machine, and only flags a health counter. Full clock-skew against *server* time is milestone
10.

## Consequences

- The whole excursion rule is tested exhaustively in milliseconds, including a seven-day soak and a
  DST crossing, with a `FakeClock`.
- The rule is one implementation the server can mirror exactly, because it is a pure function of
  `(timestamps, values, policy)`.
- Cost: the caller must supply timestamps and must feed conditioned (filtered, calibrated) values —
  the agent does both. The machine trusts the timestamps it is given; guarding against a *forward*
  clock jump is a data-quality concern handled by skew detection, not by the machine second-guessing
  the series.
