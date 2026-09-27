"""Pure decision logic: no I/O, no hardware, no real clock.

Everything here takes plain values (or an injected ``Clock``) and returns plain values, so it runs
in microseconds and is trivial to test exhaustively. This is where the excursion state machine, the
median filter, the backoff maths, batch splitting, and the LED/buzzer mapping live.
"""
