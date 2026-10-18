# Docker development build

The Dockerfile builds a Linux development/runtime image with Python 3.11, PySide6
and Debian FFmpeg/FFprobe. This is separate from the native portable release recipe;
the image explicitly includes FFmpeg as a development dependency. No image is pushed
or published by these commands. The build context allowlist excludes `.git`, local
media, `.venv`, credentials, caches and existing build artifacts.

With Docker Engine running:

```sh
# Build and execute the regression suite inside the image.
docker build --target test -t media-wrapper:test .

# Build the desktop application image.
docker build -t media-wrapper:local .

# Headless startup/binary-detection check, without mounting host files.
docker run --rm -e QT_QPA_PLATFORM=offscreen media-wrapper:local --smoke-test
```

The test stage runs as an unprivileged user, with offscreen Qt and temporary test
media. The runtime image also runs as an unprivileged user. A visible GUI requires
explicit host display/audio forwarding; the image is not a browser application and
does not build Windows executables. Media folders must be mounted explicitly when
needed; mount inputs read-only and use a separate writable output folder.

A local Docker daemon is required. If `docker version` reports no server/socket,
start your installed Docker Engine first. On this Linux system the service command
is `sudo systemctl start docker`; run it in your own terminal if sudo asks for a
password. Do not send a password to the assistant.

Verification status: Docker client/daemon binaries are installed here, but the
engine was stopped and passwordless service startup was denied. Docker image
build/run is pending engine startup; the native source suite passed separately.

Local package-build check passed with `python -m pip wheel --no-deps
--no-build-isolation`: produced the application wheel successfully. This verifies
the project packaging input, not the Docker base image, apt dependencies or image run.
