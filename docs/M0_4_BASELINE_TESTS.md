# M0.4 baseline tests and CI

75 tests passed on Linux using `.venv/bin/python -m pytest -q`; Ruff passed.
Added explicit-folder/PATH resolution tests, missing binaries, process errors,
Windows executable naming, malformed probe JSON/shapes, invalid numbers, and paths
with spaces, Unicode and leading hyphens. Fixed path normalization and malformed
metadata/non-finite values uncovered by these tests.

GitHub Actions now installs FFmpeg and project dependencies, requires working
binaries, and runs lint, unit/integration tests and offscreen Qt startup on Linux
and Windows with Python 3.11 and 3.14. Workflow guidance:
https://docs.github.com/en/actions/tutorials/build-and-test-code/python

No Git remote is configured and Windows is unavailable locally. Hosted CI has not
run; M0.4's cross-platform execution criterion and full M0 completion remain open.
The user authorized continuing with M1 while this external verification is pending.
