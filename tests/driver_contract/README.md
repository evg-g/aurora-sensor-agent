# tests/driver_contract

One behavioural suite, three implementations. `Sht4xStackContract` defines what *any* sensor stack
must do (produce a plausible, timestamped reading through the SHT4x driver). Each subclass plugs in a
different `I2CBus` — `sim`, `replay`, `real` — and inherits the same tests unchanged.

This is the lesson that makes hardware code testable: if the simulator and a recorded trace pass the
identical contract the real hardware is held to, then swapping one for another is safe, and almost
all of the agent can be developed and tested with no hardware at all.

- **sim** and **replay** run everywhere (laptop, CI): no hardware, no network, no Docker.
- **real** is skipped unless a Raspberry Pi with an SHT4x is wired up. The class still exists, so the
  contract documents exactly what the real bus is expected to satisfy. A separate test proves the
  real bus imports and constructs with no hardware libraries installed (its imports are lazy).
