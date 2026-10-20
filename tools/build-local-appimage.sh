#!/usr/bin/env bash
# Local development build only. Does not publish or invoke GitHub Actions.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
output="$repo/desktop/target/local-build"
mkdir -p "$output"/{target,cargo,cache}
build_version=0.1.3-dev.1
build_features=local-test
case "${1:-}" in
  "") ;;
  --production-candidate) build_version=0.1.3; build_features= ;;
  *) echo "Usage: $0 [--production-candidate]" >&2; exit 2 ;;
esac
cat > "$output/config.json" <<'JSON'
{"version":"0.1.3-dev.1","identifier":"info.kellerkind.gabbaproc.dev","bundle":{"createUpdaterArtifacts":false},"app":{"windows":[{"title":"GabbaProc Companion — Local development","width":920,"height":780,"minWidth":650,"minHeight":560,"resizable":false}]}}
JSON
if [[ -z "$build_features" ]]; then
  cat > "$output/config.json" <<'JSON'
{"version":"0.1.3","bundle":{"createUpdaterArtifacts":false},"app":{"windows":[{"title":"GabbaProc Companion — Release candidate","width":920,"height":780,"minWidth":650,"minHeight":560,"resizable":false}]}}
JSON
fi
podman build -t localhost/gabbaproc-appimage-build -f "$repo/deploy/companion-build.Containerfile" "$repo/deploy"
podman run --rm --security-opt label=disable \
  -v "$repo/desktop:/work/desktop" -v "$repo/server:/work/server:ro" \
  -v "$output/target:/target" -v "$output/cargo:/cache" \
  -v "$output/cache:/root/.cache" -v "$output/config.json:/tmp/local-build.json:ro" \
  -e CARGO_HOME=/cache -e CARGO_TARGET_DIR=/target -e CARGO_BUILD_JOBS=4 \
  -e BUILD_FEATURES="$build_features" -e APPIMAGE_EXTRACT_AND_RUN=1 localhost/gabbaproc-appimage-build \
  sh -c 'npm ci && cargo test --locked -p gabbaproc-companion --lib && if [ -n "$BUILD_FEATURES" ]; then npm run tauri -- build --features "$BUILD_FEATURES" --bundles appimage --config /tmp/local-build.json; else npm run tauri -- build --bundles appimage --config /tmp/local-build.json; fi'
cp "$output/target/release/bundle/appimage/GabbaProc Companion_${build_version}_amd64.AppImage" "$output/GabbaProc-Companion-${build_version}-x86_64.AppImage"
(cd "$output" && sha256sum GabbaProc-Companion-${build_version}-x86_64.AppImage > SHA256SUMS)
