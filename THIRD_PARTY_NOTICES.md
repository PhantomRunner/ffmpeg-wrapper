# Third-party notices and distribution status

This repository currently has no declared license for the application's own code.
The owner must choose that license before public distribution. These notes are a
release review record, not a declaration that a particular package is compliant.

## Dependencies included by the native packager

- Python: Python Software Foundation License and the licenses of included standard
  library components. https://docs.python.org/3/license.html
- PySide6/Shiboken6/Qt: license choice and obligations depend on the precise modules
  and binaries. The application uses Qt Widgets, Core, Gui and SVG support; optional
  WebEngine/PDF/QML application modules are excluded. Wheel-supplied license files
  are copied into licenses/. Audit the actual packaged libraries/plugins, their
  notices, replacement/relinking rights and corresponding source requirements.
  https://doc.qt.io/qtforpython-6/licenses.html
  https://www.qt.io/development/open-source-lgpl-obligations
- PyInstaller: bootloader licensing exception permits packaging applications;
  review the exact installed version's license, included in licenses/.
  https://pyinstaller.org/en/stable/license.html

Installed packages can contain other components; package names alone are not a
complete bill of materials. Record actual shipped files and dependency notices,
retain required copyright/license texts and provide applicable source/relinking
materials before approving a release. Public release remains gated on this audit.

## FFmpeg and FFprobe: not bundled

No FFmpeg origin/build has been approved for redistribution, and no binary is
included by this build pipeline. External/user-supplied sidecar installations
remain the user's selection. FFmpeg's applicable license changes with enabled
components; configurations marked nonfree are not redistributable under FFmpeg's
stated conditions. Review exact build options and all external components.
https://ffmpeg.org/legal.html

Before any binary is bundled, record the upstream source/provider URL, release
and revision, SHA256 hashes for FFmpeg/FFprobe, `-version` and `-buildconf` output,
exact source/archive and patches, reproducible build instructions, applicable
licenses, notices, and source delivery obligations. Review both binaries and their
runtime dependencies. Obtain documented release approval; never substitute an
unreviewed binary just because it runs. This milestone intentionally ships none.

Use `packaging/ffmpeg-review.template.json` as the per-build evidence record.
An empty template is not approval. The current build manifest always records
`ffmpeg_bundled: false`; adding binaries to a candidate by hand requires a fresh
inventory, checksum generation, review and installation verification.
