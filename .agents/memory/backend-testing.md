---
name: Backend test running
description: How to actually run the python-backend pytest suite in this repl
---

- `pytest` is NOT preinstalled in this repl's `python3.11`. Install it (`python3.11 -m pip install pytest`) before running the backend suite.
- The suite is large (~7500+ tests) and many tests hit live network sources that are **blocked** in this container (nseindia, moneycontrol, chittorgarh). Running the whole suite in one go times out / fails on environment, not on your code.

**How to apply:** Run targeted subsets relevant to your change, e.g.
`cd artifacts/python-backend && DISABLE_AUTH=1 python3.11 -m pytest tests/test_<x>.py -q`.
`DISABLE_AUTH=1` is the auth bypass for backend tests. Pure-math/service unit tests (no DB/network) are the reliable signal; DB-bound helpers in the synthetic engine aren't unit-tested because there's no Postgres mock in the suite.
