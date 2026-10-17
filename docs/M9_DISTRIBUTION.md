# M9 distribution implementation and local evidence

Date: 2026-10-17. M9 is **partially complete**, not release-approved.
The roadmap ends at M9; M10 scope was requested from the user, not invented.

## Implemented slices

- M9.1: explicit sidecar-folder selection and active FFmpeg/FFprobe paths plus
  versions. Missing sidecars never fall back to PATH. Real external and explicitly
  selected paired-directory detection both passed locally.
- M9.2: pinned native PyInstaller one-folder recipe, SVG window icon/Windows ICO,
  Qt runtime/plugins, documentation, source hashes, build identity, dependency
  metadata/license inventory and file checksums. Linux built successfully; Windows
  recipe is committed but not run here. Repeatable inputs are enforced; identical
  output bytes across different native systems are not claimed.
- M9.3: explicit packaged GUI verification using the existing asynchronous model.
  A temporary installation exercises Inspect, Remux, Convert and Compress with
  spaces/Unicode, a source path over 260 characters, Linux read-only source and
  separate outputs. It checks source preservation and removes only its own
  installation while retaining fixture/output/settings until temporary cleanup.
  This is a fresh portable directory on this host, not a clean-OS VM test.
- M9.4: documented dependency/FFmpeg provenance requirements and an unreviewed
  binary review template. No FFmpeg binaries are collected or redistributed.
- M9.5: native Ubuntu 24.04/Windows 2022 build/verification workflow, alongside
  the source-test Linux/Windows Python 3.11/3.14 workflow. Build/checksum reports
  may be uploaded by CI; binary archives are not uploaded pending license review.
- M9.6: candidate notes, troubleshooting, install/removal instructions and native
  release matrix. Version remains 0.1.0; no tag or public release was created.

## End-of-milestone verification

Implementation slices were committed before tests. All testing was performed in
this final verification phase, including fixes/rechecks prompted by the audit.

- `.venv/bin/pytest -q`: **329 passed in 18.61s**, no skips.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/python -m pip check`: no broken requirements.
- `git diff --check`: passed.
- `.venv/bin/python scripts/build_distribution.py`: Linux portable build passed;
  the audited candidate contains 356 inventoried files, approximately 216 MiB.
- `.venv/bin/python scripts/verify_distribution.py dist/MediaWrapper`: passed;
  all three packaged tasks Completed, source unchanged, installation removal
  passed, isolated preferences retained, SVG icon successfully rendered.
- `.venv/bin/python scripts/archive_distribution.py`: Linux tar.gz created,
  approximately 85 MiB; tar preserves required symbolic links. Archive/checksums
  are local ignored build outputs, not committed or published.
- New regression coverage checks source/frozen sidecar paths, missing binary
  refusal, active path presentation, Linux child-library environment restoration,
  Windows DLL-reset/path-filter logic (simulated), and nonempty verifier rejection.
- Existing real-media, queue/cancellation, output-safety, profiles/batch and GUI
  lifecycle tests remain passing. Domain stays Qt-independent; subprocess argv
  construction and OS environment handling remain in infrastructure.

Local build host: Linux x86_64, Arch kernel 7.2.10, glibc 2.44, Python 3.14.8,
PySide6 6.12.0, PyInstaller 6.22.0. This local artifact does **not** establish the
Ubuntu 24.04 baseline or Windows compatibility. Those native CI builds must run.
PyInstaller correctly warns that executable icons are Windows/macOS-only; Linux
uses the packaged application window icon. No other build warnings were reported.

## Open acceptance gates

1. Native Windows and hosted CI results have not been obtained. A Git remote now
   exists, but this work did not push commits, dispatch workflows or publish.
2. Clean-OS desktop, Windows ACL/long-path policy and physical GPU success/contention
   still need the matrix in RELEASE_CHECKLIST.md. M0.4 and M5.6 remain open.
3. The owner has not chosen a license for the application's own code.
4. Installed Qt/PySide6/Shiboken6 wheels contain license expressions in metadata
   but no license text files. The manifest explicitly records missing wheel
   license files. Exact required notices, source/relinking materials and shipped
   dependency review remain release blockers; metadata is not compliance proof.
5. No release tag until the preceding gates pass. M9.2/M9.3/M9.5/M9.6 checkboxes
   remain open; only M9.1 and M9.4 documentation/no-bundling policy are checked.

Next work: native distribution/CI verification and release licensing decisions.
M10 requires a user-defined objective and acceptance criteria before implementation.
