# Linux development/verification image; desktop access is explicitly supplied at run time.
ARG BASE_IMAGE=python:3.11-slim-bookworm
FROM ${BASE_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
# Bullseye is used only for the optional older-glibc packaging environment.
# Its retired security repository requires a signed, fixed archive snapshot.
RUN if grep -q 'VERSION_CODENAME=bullseye' /etc/os-release; then \
      printf '%s\n' \
        'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20260831T000000Z/ bullseye main' \
        'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/20260831T000000Z/ bullseye-security main' \
        > /etc/apt/sources.list; \
    fi
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-dejavu-core libegl1 libopengl0 libgl1 libdbus-1-3 libpulse0 libglib2.0-0 \
    libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 \
    libxcb-shape0 libxcb-xinerama0 libxcb-randr0 libxcb-render-util0 libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/media-wrapper
COPY pyproject.toml README.md ./
COPY src/ src/
COPY packaging/ packaging/
ARG APP_UID=1000
ARG APP_GID=1000
RUN python -m pip install . && groupadd --gid "$APP_GID" app \
    && useradd --create-home --uid "$APP_UID" --gid "$APP_GID" app

# Qt 6.7 Multimedia requires libatomic even on x86-64.
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS builder
USER root
RUN apt-get update && apt-get install -y --no-install-recommends git binutils \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install -r packaging/requirements.txt
ENV QT_QPA_PLATFORM=offscreen

FROM base AS test
COPY tests/ tests/
COPY scripts/ scripts/
COPY .github/ .github/
RUN python -m pip install 'pytest>=8' 'ruff>=0.7'
ENV QT_QPA_PLATFORM=offscreen
USER app
CMD ["sh", "-c", "python -m ruff check --no-cache . && python -m pytest -q -p no:cacheprovider"]

FROM base AS runtime
USER app
ENTRYPOINT ["python", "/opt/media-wrapper/packaging/launcher.py"]

FROM base AS development
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc novnc websockify openbox supervisor xauth \
    && rm -rf /var/lib/apt/lists/*
COPY docker/ /opt/desktop/
EXPOSE 6080
ENTRYPOINT ["python", "/opt/desktop/start.py"]
