# M3 operation plans and commands

M3.1: frozen Qt-independent operation, selection, output and profile models;
typed validation error codes. Model tests and Ruff pass on Linux.
Windows execution remains pending.

M3.2: separate pure policy and filesystem checks; conservative shared codec policy.
148 tests pass, including selection/conflict and overwrite preservation checks; Ruff passes.
Minimal encoding supports AAC, PCM and FFV1 only with explicit build availability.

M3.3: deterministic pure CommandBuilder for explicit copy and per-output-stream
encoding options; pure policy resides in domain. 150 tests and Ruff pass.

M3.4: explicit maps, copy plans and mandatory -n; application preparation defaults
to a unique adjacent temporary output, validates both paths and creates no files.
The existing Remux UI uses the new plan/builder with direct output explicitly
selected until staged execution and safe finalization arrive in M4/M5.
151 tests pass, including existing real Remux/UI and temporary collision checks.
