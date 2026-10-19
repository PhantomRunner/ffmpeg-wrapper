# AppImage / Windows EXE release preparation

Status: packaging preparation, not release approval. Targets requested by the owner:
Linux x86_64 AppImage and Windows x64 EXE installer (the milestone specifies an
installer). Existing PyInstaller one-folder output is the payload, not either
finished distribution format. Preserve the existing validation and processing
pipeline. No public tag/release without an explicit publication command.

## Current evidence

- Source baseline: 5499141, UX-02/03/04/05 locally verified; UX-01 remains pending.
- Existing native recipes: Linux/Windows portable folder plus tar.gz/ZIP and hashes.
- Windows native build, Windows desktop and hosted CI evidence are still pending.
- Prior local Linux candidate uses Arch/glibc 2.44; it is not evidence for the
  Ubuntu 24.04 baseline. AppImage does not remove the libc compatibility requirement.
- FFmpeg/FFprobe executables are not bundled. Qt Multimedia preview dependencies
  are part of the payload and must remain in the dependency/license inventory.
- AppImage assembly and Windows installer recipes are not implemented yet.

## Before the Windows candidate build

1. Freeze source commit, application version and Windows x64 support target.
   Build from a clean checkout on a native Windows runner with Python 3.14
   and packaging/requirements.txt. Check availability of the pinned Windows wheels.
2. Verify both FFmpeg and FFprobe resolve for integration testing. Run pip check,
   Ruff and the full pytest suite on Windows; integration tests must not silently
   skip because binaries are missing. Record results for this exact source commit.
3. Include high-DPI regression tests for parameter help, validation feedback,
   operation notifications, queue history, compact layouts, popups and playback.
4. Test Windows path/permission behavior: Cyrillic/Unicode, spaces, long paths under
   actual OS policy, existing outputs, source aliases, denied destinations,
   read-only source directories and staged publication on supported filesystems.
5. Confirm external subprocess DLL environment handling and explicit PATH/custom/
   sidecar binary selection. Missing sidecar or FFmpeg must produce actionable
   feedback, never a hidden fallback.
6. Check resources and runtime payload: Windows icon, Qt platform plugin,
   multimedia decoder/audio plugins, stylesheet/help resources, notices and
   diagnostics location. Existing PyInstaller recipe is console=False, debug=False.

## After building the Windows payload / installer

1. Run scripts/verify_distribution.py against the actual frozen folder: real
   inspect/remux/convert/compress, decoded playback, source preservation, hashes.
2. Create an EXE installer around the whole verified folder; retain runtime
   dependencies, version/icon and uninstall support. Do not distribute the
   one-folder executable alone.
3. Test installer on clean Windows 10/11 x64 without Python/developer dependencies:
   installation, shortcuts, normal-user launch, playback/audio, queue/cancel/retry,
   help/notifications/history, upgrade and uninstall. Preserve media/preferences.
4. Exercise available GPU encoders with real drivers; record unsupported/failure
   cases and explicit CPU retry. Hosted runners do not prove GPU compatibility.
5. Check the final installer with platform security tooling; record whether it is
   signed or unsigned. If release signing is used, verify signature/timestamp
   and compute final SHA-256 after signing. Never describe an unsigned candidate
   as signed or guarantee absence of SmartScreen warnings.

## Linux AppImage sequence

1. Build the existing native payload on the supported Linux baseline.
2. Add AppDir assembly with AppRun, desktop entry, icon and the complete payload.
   Pin and checksum the AppImage packaging tool used by CI.
3. Preserve explicit external FFmpeg selection; verify child process environment,
   writable per-user settings/logs and outputs outside the mounted image.
4. Test the produced AppImage, including extraction-based launch where mounting is
   unavailable, on clean baseline and newer desktop systems. Verify playback,
   Qt plugins, permissions, output safety and persistent settings.
5. Retain source/dependency manifest, build logs, native verification and final hash.

## Public release gate

UX-01, native platform acceptance, application license choice, dependency/license
review and existing RELEASE_CHECKLIST.md blockers remain open. Building a private
candidate does not waive them. Only an explicit publication command after verified
acceptance permits publishing the production release.
