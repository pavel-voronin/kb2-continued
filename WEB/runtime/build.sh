#!/usr/bin/env bash
# Run under Linux/WSL with Emscripten 5.0.2, CMake, Ninja and Git on PATH.
set -euo pipefail
web_dir="$(cd "$(dirname "$0")/.." && pwd)"
work_dir="${KB2_WASM_WORK:-$HOME/.cache/kb2-wasm}/emulators"
if [[ ! -d "$work_dir/.git" ]]; then
  mkdir -p "$(dirname "$work_dir")"
  GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 --branch v8.5.3 \
    https://github.com/js-dos/emulators.git "$work_dir"
fi
cd "$work_dir"
test "$(git rev-parse HEAD)" = e6f4e5449a5b17ae3ea0fdccfd453c8d299e9ea5
git -c url.https://github.com/.insteadOf=git@github.com: \
  submodule update --init --depth 1 native/dosbox native/dosbox-x
if git apply --check "$web_dir/runtime/fastlaunch.patch" 2>/dev/null; then
  git apply "$web_dir/runtime/fastlaunch.patch"
else
  git apply --reverse --check "$web_dir/runtime/fastlaunch.patch"
fi
if git -C native/dosbox-x apply --check "$web_dir/runtime/fastlaunch-ega.patch" 2>/dev/null; then
  git -C native/dosbox-x apply "$web_dir/runtime/fastlaunch-ega.patch"
else
  git -C native/dosbox-x apply --reverse --check "$web_dir/runtime/fastlaunch-ega.patch"
fi
if git apply --check "$web_dir/runtime/jsdos-integration.patch" 2>/dev/null; then
  git apply "$web_dir/runtime/jsdos-integration.patch"
else
  git apply --reverse --check "$web_dir/runtime/jsdos-integration.patch"
fi
if git -C native/dosbox-x apply --check "$web_dir/runtime/startup-keyboard.patch" 2>/dev/null; then
  git -C native/dosbox-x apply "$web_dir/runtime/startup-keyboard.patch"
else
  git -C native/dosbox-x apply --reverse --check "$web_dir/runtime/startup-keyboard.patch"
fi
if git -C native/dosbox-x apply --check "$web_dir/runtime/startup-video.patch" 2>/dev/null; then
  git -C native/dosbox-x apply "$web_dir/runtime/startup-video.patch"
else
  git -C native/dosbox-x apply --reverse --check "$web_dir/runtime/startup-video.patch"
fi
if git -C native/dosbox-x apply --check "$web_dir/runtime/save-files.patch" 2>/dev/null; then
  git -C native/dosbox-x apply "$web_dir/runtime/save-files.patch"
else
  git -C native/dosbox-x apply --reverse --check "$web_dir/runtime/save-files.patch"
fi
emcc --version | head -1 | grep -F '5.0.2'
emcmake cmake -S . -B build/wasm -G Ninja -DCMAKE_BUILD_TYPE=Release -DDOSBOX_DEBUG=OFF
cmake --build build/wasm --target wdosbox-x -j4
node "$web_dir/runtime/package.cjs" "$work_dir/build/wasm"
