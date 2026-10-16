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

M3.5: 171 tests pass with `.venv/bin/python -m pytest -q`;
`.venv/bin/ruff check .` and `git diff --check` pass. Negative coverage includes
missing/duplicate streams, wrong encoder kind, unavailable encoders, invalid
bitrates, copy conflicts, incompatible codecs/containers, hardlinks, missing
inputs/directories, reserved filenames and existing outputs. Mixed copy/encode
commands use output stream positions even when source indices are reordered.
Real generated PCM audio verifies staged copy to Matroska and encoding to AAC/MP4;
inspection confirms output codecs and repeated execution preserves output bytes.
This local FFmpeg can report overwrite refusal with exit status zero; tests also
check refusal diagnostics. The process runner must not infer success from exit
status alone when finalizing output. Existing UI/startup/Remux tests still pass.

The minimal Convert API is intentionally narrow: AAC (optional positive bitrate),
PCM s16le and FFV1, plus copy. No arbitrary arguments, scaling, CRF, GPU, production
capability discovery or Convert UI is introduced. Callers supply build encoder
availability; defaults deny encoding. Broader options belong to M6/M7.
Preparation is synchronous application work intended for workers. It validates
paths before generation; the pure builder only checks structural policy. Planned
temporary names are not reserved; -n refuses a collision. Publication must check
the final destination again and must never overwrite it (M4/M5).

Windows native/hosted CI remains unavailable. Next: M5.1 common process runner
then M5.2 progress, as required before M4 staged execution.
