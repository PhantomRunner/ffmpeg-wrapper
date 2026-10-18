# Release gates and native verification matrix

Keep this file with each candidate's evidence. A checked code task is not proof
that a binary was tested on another operating system.

| Check | Linux local | Windows native | Hosted CI |
| --- | --- | --- | --- |
| Unit/integration/lint | 329 passed; lint passed | Pending | Pending |
| Portable build, checksums, icon and Qt plugins | Passed on local Arch/glibc 2.44 | Pending | Pending |
| Fresh path with spaces/Unicode, inspect/remux/convert/compress | Passed (temporary install) | Pending | Pending |
| Remove installation; preserve media/preferences | Passed (temporary install) | Pending | Pending |
| Read-only source, separate writable destination | Passed | ACL test pending | Pending |
| Denied destination, existing output, partial retained | Test suite | Pending | Pending |
| Long paths under target OS policy | Passed (over 260 chars) | Pending | Pending |
| Real desktop launch and cancellation | Offscreen only | Pending | Offscreen only |
| NVENC / QSV / AMF / VAAPI success and failure | No usable GPU | Pending | Hardware unavailable |

Manual steps: use a fresh OS/user profile, install/copy the candidate, select both
PATH/custom and explicit sidecar modes, inspect a media fixture and run Remux,
Convert, Compress, cancel and retry. Repeat with spaces/Unicode paths, a read-only
source, denied output directory and a long path allowed by that OS. Confirm no
source/destination replacement. Remove only the installation and confirm user
media/settings survive. Record OS, architecture, Python/Qt/FFmpeg versions,
bundle checksum and results. GPU rows require hardware/driver identity and actual
short encode results, including explicit CPU retry on a failed GPU attempt.

Before creating a public version tag:

- Owner selects the application license.
- Native Linux/Windows builds and installation tests pass; CI evidence is linked.
- Audit exact shipped dependency libraries, notices and source/relinking materials.
- No FFmpeg sidecar is included without the documented binary compliance review.
- Known limitations and troubleshooting match verified behavior.
- Record final source commit, checksums and release approval, then create the tag.

No public release or release tag is created while these gates remain unresolved.

CI definitions: `.github/workflows/tests.yml` runs unit/integration/lint on Linux
and Windows with Python 3.11/3.14. `distribution.yml` builds native candidates on
Ubuntu 24.04 and Windows 2022/Python 3.14, runs the packaged installation verifier,
and retains build/checksum inventories for seven days. Binary archives stay on the
runner pending dependency/license review; they are not uploaded automatically. Linux uses tar.gz to preserve
symlinks; Windows uses ZIP. These workflows do not create tags or releases.
Record their actual run URLs and results here before checking hosted verification.

## UX remediation candidate — 2026-10-18

This supplements the historical matrix above. Local source verification: 384 passing
tests, full Ruff and whitespace checks. At 200% scale: 44 passing workspace, theme,
extension/dropdown, encoding and playback tests. Native Linux candidate built on
Arch/glibc 2.44 with Python 3.14.8, Qt/PySide6 6.12.0, PyInstaller 6.22.0; pinned
build inputs passed. The candidate manifest records the development tree as dirty.

Portable installation/removal/checksum verification passed in a fresh path with
spaces/Unicode and read-only long-path source: Inspect, Remux, Convert, Compress,
three Completed tasks, decoded preview video and position 116 ms; source unchanged.
Qt Multimedia preview dependencies are inventoried in `preview_media_libraries`.
No processing FFmpeg/FFprobe executable is included.

Native Windows, actual hosted workflow runs, physical audio/display/GPU acceptance,
oldest supported Linux baseline and existing license/dependency release gates remain
pending. No public release approval is implied. See UX_REMEDIATION_PLAN.md for scope.
