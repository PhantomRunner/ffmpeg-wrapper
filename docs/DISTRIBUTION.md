# Portable distribution builds

Build on the target OS: PyInstaller output is native to its OS, Python and CPU
architecture. Linux builds must use the oldest supported glibc baseline; current
CI uses Ubuntu 24.04, targeting that release or newer compatible systems. Windows
CI uses Windows Server 2022, targeting Windows 10/11 x64 subject to native checks.
These are candidate support targets, not evidence of successful installs.

From a clean checkout on each target, using Python 3.14:

```
python -m venv .venv-build
# Activate .venv-build using your shell's normal activation command.
python -m pip install -r packaging/requirements.txt
python -m pip install --no-deps --no-build-isolation .
python scripts/build_distribution.py
python scripts/verify_distribution.py dist/MediaWrapper
```

The pinned inputs, native runner, build-info.json and SHA256SUMS.json make the
build traceable and repeatable. Builds enforce the pinned package versions and record source hashes and dirty-tree
status. Byte-for-byte reproducibility across machines is
not claimed. Use a clean build environment; the manifest records actual versions.
The builder refuses an existing output folder. Move a previous build aside before
rebuilding. No build script downloads or includes FFmpeg/FFprobe binaries.

The folder includes Qt runtime/plugins discovered by PyInstaller, the application
icon, documentation, wheel-provided license files and checksums. Keep the entire
folder together. Start MediaWrapper on Linux or MediaWrapper.exe on Windows.
Linux additionally needs the platform's graphics/system libraries; offscreen CI
does not replace testing a real desktop. See the release checklist before sharing. The build inventory explicitly lists wheels missing license files;
package METADATA is retained but is not a substitute for required license texts.

In Settings, choose external PATH, a custom folder containing both binaries, or
explicitly select a sidecar at `ffmpeg/bin` beside the executable. An incomplete
sidecar fails detection without falling back to PATH. Paths and both version
lines are shown. Sidecars are user-supplied until the compliance gate is satisfied.

## Installation and removal

Extract/copy the whole folder into a writable location. No elevated installation,
registry changes or PATH modification is performed. Close the app and remove only
that installation folder to uninstall. Media outputs, profiles, queue definitions,
retained partial files and per-user settings/logs remain. Remove preferences/logs
only deliberately, using the locations displayed by the application (README).

The automated portable check copies the built folder to a fresh path containing
spaces/Unicode, creates a tiny video/audio fixture, runs the packaged GUI through
Inspect/Remux/Convert/Compress, verifies source preservation, and removes only its
own temporary installation. The fixture uses a long path (over 260 characters); Linux also makes the source
directory read-only.
Windows ACL, real desktop, long-path policy and GPU checks require the native
manual matrix; a Windows read-only file attribute is not an ACL write restriction.

`MediaWrapper --verify-install SOURCE EMPTY_DIRECTORY` is an explicit diagnostic
mode. It uses an isolated config/log directory inside EMPTY_DIRECTORY and produces
three outputs plus verification.json (including decoded video and playback position); it requires a short video/audio fixture and
external PATH FFmpeg with FFV1, PCM, libx264 and AAC. It never replaces existing
outputs. The verifier supplies a subprocess timeout. `--smoke-test` starts the
ordinary desktop and exits after binary detection with status 0 or 2.

## Troubleshooting

- Binary detection: inspect the two paths/version lines and select a complete
  installation. Missing sidecars do not trigger an automatic fallback.
- Qt platform plugin errors: preserve the whole bundle; install required platform
  libraries and check graphics/session compatibility. Do not copy arbitrary Qt
  plugins from another installation.
- Output publication needs same-filesystem hard links. Choose a supported local
  filesystem; failed publication retains and identifies the partial file.
- GPU listing does not prove runtime support. Scan/test on the actual device;
  explicitly retry on CPU when necessary.
- Invalid saved definitions, changed sources or existing outputs require review
  and fresh filenames. No mid-encode checkpoints are supported.

Build-system reference: https://pyinstaller.org/en/stable/operating-mode.html

## UX remediation candidate

The installation verifier now waits for each asynchronous queue validation before
starting the queue, then checks an actual decoded preview frame and advancing
playback position. Qt Multimedia needs the platform multimedia/audio libraries even
in offscreen tests. On restricted execution sandboxes, denied local audio IPC can
prevent backend initialization; run native verification with local IPC access.
The inventory now separately lists preview media libraries. Processing executables
remain external or explicitly selected sidecars; public release gates are unchanged.

## Preparing a release candidate

After native verification, run `python scripts/archive_distribution.py`.
Archives include the application version, OS, architecture and source commit;
a matching `.sha256` file verifies the download. Existing archives are never
overwritten. Linux archives preserve symbolic links; Windows produces ZIP.

The "Native distribution verification" workflow can be dispatched with
`candidate_archives=true` to retain verified Windows/Linux portable archives
and checksums for 14 days. The default still uploads inventories only.
This uploads workflow artifacts, not a GitHub Release, tag or installer.
Use the Ubuntu runner for the supported glibc baseline; an archive built on a
newer local distribution is only verified for that host. License and native
desktop acceptance gates in RELEASE_CHECKLIST.md still apply before publication.
