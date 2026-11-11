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

Each GitHub release includes `KB2-emulator-source.tar.gz` alongside the website
archive: https://github.com/pavel-voronin/kb2-continued/releases . It contains
the patched emulator source, its DOSBox submodules, third-party source, the
upstream npm package (including JavaScript source maps), and our patches.
These sources are not downloaded during gameplay.

Our changes are the adjacent `.patch` files: fast launch with EGA setup,
temporary startup CPU boost, and a save-file/exit bridge. Pascal sources and
game executables are not patched by the web packager.

To rebuild from the project checkout, activate Emscripten 5.0.2 and install Git,
CMake, Ninja and Node.js, then run `bash WEB/runtime/build.sh`. It fetches the
pinned source, applies the patches and updates `runtime/vendor` and its hashes.
For the already patched source archive, activate the same SDK and run inside
`emulators/`:

```sh
emcmake cmake -S . -B build/wasm -G Ninja -DCMAKE_BUILD_TYPE=Release -DDOSBOX_DEBUG=OFF
cmake --build build/wasm --target wdosbox-x -j4
```

The matching browser worker/footer comes from the npm JavaScript bundle;
`package.cjs` preserves this footer when replacing the native module.
`vendor/manifest.json` records the exact shipped binary hashes.
