#!/usr/bin/env bash
# Build and verify an AppImage using the compatible, pinned Docker environment.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: scripts/build_appimage.sh [--reuse-bundle] [--skip-image-build]

Build the Docker packaging image, fetch checksum-pinned AppImage tools, build
and verify the portable application, then assemble and verify its AppImage.
Results are written to dist/; existing artifacts are never removed.

  --reuse-bundle       Verify and package the existing dist/MediaWrapper folder.
  --skip-image-build  Use the existing media-wrapper-builder:compat Docker image.
  -h, --help          Show this help.

Requires Linux x86-64, Docker, and network access for uncached build dependencies.
HELP
}

reuse_bundle=0
skip_image_build=0
for argument in "$@"; do
    case "$argument" in
        --reuse-bundle) reuse_bundle=1 ;;
        --skip-image-build) skip_image_build=1 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$argument" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
    printf 'AppImage assembly requires Linux x86-64.\n' >&2
    exit 1
fi

script_directory=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repository=$(CDPATH= cd -- "$script_directory/.." && pwd)
bundle="$repository/dist/MediaWrapper"
if [[ $reuse_bundle == 1 ]]; then
    if [[ ! -d "$bundle" ]]; then
        printf 'No portable bundle found at %s; omit --reuse-bundle to build it.\n' "$bundle" >&2
        exit 1
    fi
elif [[ -e "$bundle" ]]; then
    printf 'dist/MediaWrapper already exists. Use --reuse-bundle or preserve the previous build elsewhere.\n' >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    printf 'Docker is required. Install Docker and start its daemon before building.\n' >&2
    exit 1
fi
docker info >/dev/null

builder_image=media-wrapper-builder:compat
if [[ $skip_image_build == 0 ]]; then
    docker build --build-arg BASE_IMAGE=python:3.11-slim-bullseye \
        --target builder --tag "$builder_image" "$repository"
fi

docker run --rm --user "$(id -u):$(id -g)" --env HOME=/tmp \
    --volume "$repository:/work" --workdir /work "$builder_image" \
    sh -ec '
        python scripts/build_appimage.py --download-tools --tools-only
        if [ "$1" != 1 ]; then
            python scripts/build_distribution.py
        fi
        python scripts/verify_distribution.py dist/MediaWrapper
        python scripts/build_appimage.py --verify
    ' appimage-build "$reuse_bundle"
