# Summary

<!-- What does this change and why? -->

## Testing checklist

- [ ] `make ci-local` passes locally (no hardware / network / Docker)
- [ ] New behaviour has tests at the right tier (unit / driver-contract / fault / ...)
- [ ] Determinism kept: no real sleep, no real clock, seeded RNG
- [ ] `hil` tests (if any) are marked and deselected by default
- [ ] No `TODO`/placeholder in the diff
- [ ] Non-obvious decisions captured in an ADR
