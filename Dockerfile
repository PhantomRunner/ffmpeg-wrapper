# Linux development/verification image; desktop access is explicitly supplied at run time.
FROM python:3.11-slim-trixie AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-dejavu-core libegl1 libopengl0 libgl1 libdbus-1-3 libpulse0 libglib2.0-0 \
    libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 \
    libxcb-shape0 libxcb-xinerama0 libxcb-randr0 libxcb-render-util0 libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/media-wrapper
COPY pyproject.toml README.md ./
COPY src/ src/
COPY packaging/ packaging/
RUN python -m pip install . && useradd --create-home --uid 1000 app

FROM base AS test
COPY tests/ tests/
COPY docs/ docs/
COPY scripts/ scripts/
COPY .github/ .github/
COPY AGENTS.md CHANGELOG.md THIRD_PARTY_NOTICES.md FFMPEG_CODEX_ROADMAP.md ./
RUN python -m pip install 'pytest>=8' 'ruff>=0.7'
ENV QT_QPA_PLATFORM=offscreen
USER app
RUN python -m ruff check --no-cache . && python -m pytest -q -p no:cacheprovider

FROM base AS runtime
USER app
ENTRYPOINT ["python", "/opt/media-wrapper/packaging/launcher.py"]
