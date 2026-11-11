#!/usr/bin/env bash
# Corresponding source is a separate release download, not part of page startup.
set -euo pipefail
runtime_dir="$(cd "$(dirname "$0")" && pwd)"
archive="$(realpath -m "$1")"
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
GIT_LFS_SKIP_SMUDGE=1 git clone -q --depth 1 --branch v8.5.3 https://github.com/js-dos/emulators.git "$work/emulators"
cd "$work/emulators"
test "$(git rev-parse HEAD)" = e6f4e5449a5b17ae3ea0fdccfd453c8d299e9ea5
git -c url.https://github.com/.insteadOf=git@github.com: submodule update -q --init --depth 1 native/dosbox native/dosbox-x
git apply "$runtime_dir/fastlaunch.patch" "$runtime_dir/jsdos-integration.patch"
for patch in fastlaunch-ega startup-keyboard startup-video save-files; do
  git -C native/dosbox-x apply "$runtime_dir/$patch.patch"
done
mkdir -p "$work/third-party" "$work/kb2-patches"
cp "$runtime_dir/"*.patch "$runtime_dir/build.sh" "$runtime_dir/package.cjs" "$runtime_dir/vendor/manifest.json" "$work/kb2-patches/"
fetch_source() {
  mkdir "$work/third-party/$1"
  curl --fail --location --retry 3 --silent --show-error "$2" | tar -xz --strip-components=1 -C "$work/third-party/$1"
}
fetch_source gl4es https://github.com/ptitSeb/gl4es/archive/a744af14d4afbda77bf472bc53f43b9ceba39cc0.tar.gz
fetch_source SDL2 https://github.com/libsdl-org/SDL/archive/refs/tags/release-2.32.10.tar.gz
fetch_source zlib https://github.com/madler/zlib/archive/refs/tags/v1.3.1.tar.gz
curl --fail --location --retry 3 --silent --show-error https://registry.npmjs.org/emulators/-/emulators-8.5.3.tgz -o "$work/third-party/emulators-8.5.3-npm.tgz"
cp "$runtime_dir/SOURCES.md" "$work/BUILD.md"
tar --exclude=.git --exclude=build --exclude=test --exclude=tests --exclude=dist \
    --exclude=emulators/native/dosbox-x/contrib --exclude=emulators/native/dosbox-x/ref \
    --exclude=emulators/native/dosbox-x/build-scripts/mingw/lowend-bin \
    --exclude=emulators/native/dosbox-x/vs/sdl2net/Xcode \
    --exclude=third-party/gl4es/traces \
    -czf "$archive" -C "$work" emulators third-party kb2-patches BUILD.md
