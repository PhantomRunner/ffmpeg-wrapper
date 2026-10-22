# FFmpeg UI Wrapper

MVP early access Cross-platform UI for FFmpeg in development process.

## In progress
- UI Refactoring
- Windows compatibility

Deployed features:
- media metadata inspection
- remux into Matroska, MP4, MOV, WebM, WAV or FLAC containers
- Converting and Compress, 
- Quality/bitrate controls.
- Source preview

## Run with Docker (Linux, Windows or macOS)

Install Docker Engine with the Compose plugin on Linux, or Docker Desktop using
Linux containers on Windows/macOS. From this repository's directory run:

```bash
docker compose up --build
```

Open [the application desktop](http://localhost:6080/vnc.html?autoconnect=1&resize=scale).
This runs the real Qt desktop application inside a virtual Linux desktop; noVNC
shows that desktop in your browser. It does not open a native host window.
Python, Qt and FFmpeg are installed inside the image, not on your host.
The current compatibility build targets Linux x86-64; other architectures and
Docker Desktop hosts still require native verification.

Put input files in `media/`; select `/media` in the application's file picker.
Choose `/output` for results, which appear in `output/` on your computer.
Inputs are mounted read-only; settings persist in a Docker volume. Processing
uses CPU by default. Browser preview has no audio forwarding; output audio is
still processed. The browser port binds only to localhost and has no login.

Stop with Ctrl+C, or `docker compose down` if running detached. Wait for jobs to
finish or cancel them before stopping. Start detached with
`docker compose up --build -d`; inspect health with `docker compose ps` and logs
with `docker compose logs --tail=100 app`. Do not add `down -v` unless you intend
to delete stored application settings.

Optional: copy `.env.example` to `.env` to change the port, input/output paths, or
Linux file-owner IDs (`APP_UID`/`APP_GID`, from `id -u` / `id -g`). Rebuild after
changing IDs. Existing nonempty output directories must be writable by that user.
For development, `src/` is mounted into the container; restart the application
after editing with `docker compose restart app`.

Run the isolated test container (it does not mount your media):

```bash
docker compose --profile test run --build --rm tests
```

## Requirements for running from source

- Python **3.11 or 3.12** (3.13+ is not supported by the pinned Qt release).
- **PySide6 6.7.3**, including matching Essentials, Addons and shiboken6, installed
  automatically by pip. This pins the project's minimum Qt series instead of
  silently upgrading to a newer Qt/glibc requirement.
- FFmpeg and FFprobe on PATH, or both in a directory selected in Settings.
- Linux: a graphical X11/Wayland session, glibc-based distribution, and Qt system
  libraries. On Debian/Ubuntu install:

```bash
sudo apt-get update
sudo apt-get install ffmpeg libegl1 libopengl0 libgl1 libdbus-1-3 libpulse0 \
  libglib2.0-0 libatomic1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 \
  libxcb-keysyms1 libxcb-shape0 libxcb-xinerama0 libxcb-randr0 \
  libxcb-render-util0 libx11-xcb1 fonts-dejavu-core
```

The [Qt 6.7.3 x86-64 wheels](https://download.qt.io/official_releases/QtForPython/pyside6/)
have a glibc 2.28 baseline. Our portable Linux build
uses Debian 11/Bullseye (glibc **2.31**) and requires compatible system libraries;
it does not support Alpine/musl. As [PyInstaller documents](https://pyinstaller.org/en/stable/usage.html),
building on a newer host can raise the binary's minimum glibc version. Docker supplies its own userspace libraries and avoids
requiring these Qt/glibc versions on the host. Windows compatibility is still
being verified.

## Use (PyCharm terminal or OS terminal)

Windows compatibility not verified, still in development
```bash
python -m venv .venv
```

Activate environment on Linux:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install and launch:

```bash
python -m pip install -e ".[dev]"
python -m media_wrapper.main
```

Run tests:

```bash
python -m pytest -q
```

## Assemble a Linux binary and AppImage

Build the portable binary in the older Linux environment rather than on a modern
host. Run from the repository root on Linux x86-64:

```bash
docker build --build-arg BASE_IMAGE=python:3.11-slim-bullseye \
  --target builder -t media-wrapper-builder:compat .
# Preserve any existing dist/MediaWrapper folder before building again.
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD:/work" -w /work media-wrapper-builder:compat \
  sh -c 'python scripts/build_distribution.py && python scripts/verify_distribution.py dist/MediaWrapper && python scripts/archive_distribution.py'
```

The desktop Docker service uses maintained Debian 12; the packaging command above
uses a frozen Debian 11 archive solely to lower the binary glibc baseline.

The executable is `dist/MediaWrapper/MediaWrapper`. Keep the entire folder
including `_internal`; Python is bundled, processing FFmpeg/FFprobe are external.
The archive and its SHA-256 checksum are placed in `dist/`.

For an AppImage, place the official `appimagetool-x86_64.AppImage` and
`runtime-x86_64` in `build/appimage-tools/`, using the URLs and exact SHA-256
hashes in `packaging/appimage-tools.json`. Mark appimagetool executable. Continuous
upstream downloads can change: a checksum mismatch must be reviewed, not bypassed.
Then run:

```bash
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD:/work" -w /work media-wrapper-builder:compat \
  python scripts/build_appimage.py
# Replace the example filename with the exact generated path.
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD:/work" -w /work media-wrapper-builder:compat \
  python scripts/verify_distribution.py dist/MediaWrapper \
  --appimage dist/MediaWrapper-VERSION-Linux-x86_64-COMMIT.AppImage
```

Normal AppImage launch needs FUSE 2 support (`libfuse2` on Debian 11); where FUSE
is unavailable use `APPIMAGE_EXTRACT_AND_RUN=1 ./MediaWrapper-....AppImage`.
AppImage does not bundle glibc or processing FFmpeg. Packaging does not remove
system-library requirements. Builds are verification candidates, not a published
production release; Windows and other-device desktop checks remain necessary.
