# Release gates and native verification matrix

Keep this file with each candidate's evidence. A checked code task is not proof
that a binary was tested on another operating system.

| Check | Linux local | Windows native | Hosted CI |
| --- | --- | --- | --- |
| Unit/integration/lint | Pending M9 end | Pending | Pending |
| Portable build, checksums, icon and Qt plugins | Pending | Pending | Pending |
| Fresh path with spaces/Unicode, inspect/remux/convert/compress | Pending | Pending | Pending |
| Remove installation; preserve media/preferences | Pending | Pending | Pending |
| Read-only source, separate writable destination | Pending | ACL test pending | Pending |
| Denied destination, existing output, partial retained | Test suite | Pending | Pending |
| Long paths under target OS policy | Pending | Pending | Pending |
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
and retains candidate archives for seven days. Linux uses tar.gz to preserve
symlinks; Windows uses ZIP. These workflows do not create tags or releases.
Record their actual run URLs and results here before checking hosted verification.
