# tests/soak — seven simulated days, compressed

A soak test runs the agent for a long simulated time and checks nothing degrades. Because the agent
takes an injected `Clock`, "seven days" of samples run in a fraction of a second on a `FakeClock` —
no real waiting, fully deterministic.

`test_soak.py` proves:

- **No memory growth** — `tracemalloc` shows live memory does not creep over ~1800 cycles. A per-cycle
  leak (an unbounded list, a cache that never evicts) would show up here.
- **No buffer leak** — during a simulated two-day network outage the buffer fills but never exceeds
  its capacity, then drains to empty once the uplink returns.
- **Correct across a DST change** — the run spans the European spring-forward. The device stamps UTC
  and the excursion timers use elapsed time, so a local-clock DST jump changes nothing; every cycle
  still yields a reading across the boundary.

Run it alone with `make soak`.
