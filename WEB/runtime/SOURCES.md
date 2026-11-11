# Browser DOSBox-X runtime

The game is a separate DOS program. Its original rights and the reconstruction's
license are described in `licenses/ORIGINAL-GAME.txt` and `PROJECT-LICENSE.txt`.
The modified browser emulator is distributed under GPL-2.0-or-later; license
texts and upstream notices are in `licenses/`.

Pinned upstream source:

- https://github.com/js-dos/emulators/tree/e6f4e5449a5b17ae3ea0fdccfd453c8d299e9ea5 (v8.5.3)
- DOSBox-X: https://github.com/js-dos/dosbox-x/tree/788fde99d3d451eab3621009186e5abe516f2b9c
- gl4es: https://github.com/ptitSeb/gl4es/tree/a744af14d4afbda77bf472bc53f43b9ceba39cc0
- SDL 2.32.10 and zlib 1.3.1, fetched by Emscripten 5.0.2.

Upstream source downloads:

- https://github.com/js-dos/emulators/archive/e6f4e5449a5b17ae3ea0fdccfd453c8d299e9ea5.tar.gz
- https://github.com/js-dos/dosbox-x/archive/788fde99d3d451eab3621009186e5abe516f2b9c.tar.gz
- https://github.com/ptitSeb/gl4es/archive/a744af14d4afbda77bf472bc53f43b9ceba39cc0.tar.gz
- https://github.com/libsdl-org/SDL/archive/refs/tags/release-2.32.10.tar.gz
- https://github.com/madler/zlib/archive/refs/tags/v1.3.1.tar.gz
- https://registry.npmjs.org/emulators/-/emulators-8.5.3.tgz (JavaScript source maps)

Our changes are the adjacent `.patch` files: fast launch with EGA setup,
temporary startup CPU boost, and a save-file/exit bridge. Pascal sources and
game executables are not patched by the web packager.

To rebuild from the project checkout, activate Emscripten 5.0.2 and install Git,
CMake, Ninja and Node.js, then run `bash WEB/runtime/build.sh`. It fetches the
pinned source, applies the patches and updates `runtime/vendor` and its hashes.

The matching browser worker/footer comes from the npm JavaScript bundle;
`package.cjs` preserves this footer when replacing the native module.
`vendor/manifest.json` records the exact shipped binary hashes.
