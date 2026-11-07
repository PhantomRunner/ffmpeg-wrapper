#!/usr/bin/env bash
# Build and verify the Linux AppImage and portable archive in the compatible builder.
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: scripts/build_appimage.sh [--output-dir DIR] [--reuse-bundle] [--skip-image-build]
                               [--offline-tools] [--skip-tests]

Build the Docker packaging image, fetch checksum-pinned AppImage tools, build
and verify the portable application, then assemble and verify its AppImage and tar.gz.
Results are written to dist/; existing artifacts are never removed.

  --reuse-bundle       Verify and package the existing dist/MediaWrapper folder.
  --skip-image-build  Use the existing media-wrapper-builder:compat Docker image.
  --output-dir DIR    Output directory (relative paths are relative to the repository).
  --offline-tools     Use cached AppImage tools without any downloads.
  --tools-manifest FILE  Explicit tool pins, relative to the repository (no automatic fallback).
  --skip-tests        Skip source tests; all packaged application checks still run.
  -h, --help          Show this help.

Requires Linux x86-64, Docker, and network access for uncached build dependencies.
HELP
}

reuse_bundle=0
skip_image_build=0
output_argument=dist
release_arguments=()
container_network=()
tools_manifest=
while [[ $# -gt 0 ]]; do
    case "$1" in
        --reuse-bundle) reuse_bundle=1; release_arguments+=(--reuse-bundle); shift ;;
        --skip-image-build) skip_image_build=1; shift ;;
        --offline-tools) release_arguments+=("$1"); container_network=(--network none); shift ;;
        --skip-tests) release_arguments+=("$1"); shift ;;
        --output-dir)
            if [[ $# -lt 2 || -z $2 || $2 == --* ]]; then
                printf '%s\n' '--output-dir requires a directory.' >&2; exit 2
            fi
            output_argument=$2; shift 2 ;;
        --tools-manifest)
            if [[ $# -lt 2 || -z $2 || $2 == --* || $2 == /* ]]; then
                printf '%s\n' '--tools-manifest requires a file relative to the repository.' >&2; exit 2
            fi
            tools_manifest=$2; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
    printf 'AppImage assembly requires Linux x86-64.\n' >&2
    exit 1
fi

script_directory=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repository=$(CDPATH= cd -- "$script_directory/.." && pwd)
if [[ -n $tools_manifest ]]; then
    release_arguments+=(--tools-manifest "/work/$tools_manifest")
fi
case "$output_argument" in
    /*) output_dir=$output_argument ;;
    *) output_dir="$repository/$output_argument" ;;
esac
bundle="$output_dir/MediaWrapper"
if [[ $reuse_bundle == 1 ]]; then
    if [[ ! -d "$bundle" ]]; then
        printf 'No portable bundle found at %s; omit --reuse-bundle to build it.\n' "$bundle" >&2
        exit 1
    fi
elif [[ -e "$bundle" ]]; then
    printf '%s already exists. Choose --output-dir, use --reuse-bundle or preserve the previous build elsewhere.\n' "$bundle" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    printf 'Docker is required. Install Docker and start its daemon before building.\n' >&2
    exit 1
fi
mkdir -p "$output_dir/reports"
output_dir=$(CDPATH= cd -- "$output_dir" && pwd)
reports=$(mktemp -d "$output_dir/reports/bootstrap-XXXXXX")
current_stage=preparation
write_status() {
    printf '{"success": %s, "stage": "%s"}\n' "$1" "$current_stage" >"$reports/release-status.json"
}
write_status false
trap 'write_status false; printf "Build failed; logs: %s\n" "$reports" >&2' ERR
docker info >"$reports/docker-info.log" 2>&1

builder_image=media-wrapper-builder:compat
if [[ $skip_image_build == 0 ]]; then
    docker build --build-arg BASE_IMAGE=python:3.11-slim-bullseye \
        --target builder --tag "$builder_image" "$repository" 2>&1 | tee "$reports/docker-build.log"
fi

current_stage=native
docker run --rm "${container_network[@]}" --user "$(id -u):$(id -g)" --env HOME=/tmp \
    --volume "$repository:/work" --volume "$output_dir:/distribution" --workdir /work "$builder_image" \
    python scripts/build_release.py --output-dir /distribution "${release_arguments[@]}" \
    2>&1 | tee "$reports/native-build.log"

# Independent userspaces catch accidental reliance on the builder's Python/Qt install.
for runtime in debian11 ubuntu22; do
    current_stage=$runtime
    case "$runtime" in
        debian11) base=python:3.11-slim-bullseye ;;
        ubuntu22) base=ubuntu:22.04 ;;
    esac
    runtime_image="media-wrapper-verify:$runtime"
    if [[ $skip_image_build == 0 ]]; then
        docker build --build-arg "BASE_IMAGE=$base" --file "$repository/packaging/Dockerfile.verify" \
            --tag "$runtime_image" "$repository" 2>&1 | tee "$reports/$runtime-image.log"
    fi
    docker run --rm --network none --user "$(id -u):$(id -g)" --env HOME=/tmp \
        --volume "$repository:/work:ro" --volume "$output_dir:/distribution" --workdir /work \
        "$runtime_image" python3 scripts/verify_linux_runtime.py /distribution \
        2>&1 | tee "$reports/$runtime-verify.log"
done
current_stage=complete
write_status true
printf 'Linux release verified on Debian 11 and Ubuntu 22.04: %s\nReport: %s\n' "$output_dir" "$reports/release-status.json"
