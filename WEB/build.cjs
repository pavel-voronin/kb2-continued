// Compile unmodified DOS programs with DOSBox; ship DOSBox-X for browser playback.
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { zipSync } = require('fflate');
require('emulators');
const root = path.resolve(__dirname, '..');
const out = path.join(__dirname, 'dist');
const work = path.join(__dirname, '.build');
fs.mkdirSync(work, { recursive: true });
fs.mkdirSync(path.join(out, 'vendor'), { recursive: true });
fs.mkdirSync(path.join(out, 'games'), { recursive: true });
const runtime = path.join(__dirname, 'node_modules/emulators/dist');
emulators.pathPrefix = runtime + path.sep;
const conf = (commands, build = false) => `[dosbox]\nmachine=ega\nmemsize=16\n[cpu]\ncore=normal\ncputype=286\ncycles=${build ? 'max' : 'fixed 3000'}\n[render]\naspect=false\nscaler=none\n[mixer]\nrate=44100\nprebuffer=0\n[dos]\nxms=false\nems=false\numb=false\n[autoexec]\n@echo off\nmount c .\nc:\n${commands}\n`;
function files(dir, prefix = '') {
  const result = {};
  for (const f of fs.readdirSync(dir, { withFileTypes: true })) {
    const name = prefix + f.name;
    if (f.isDirectory()) Object.assign(result, files(path.join(dir, f.name), name + '/'));
    else result[name] = new Uint8Array(fs.readFileSync(path.join(dir, f.name)));
  }
  return result;
}
async function build(mode) {
  const input = { 'SRC/': new Uint8Array(), 'SRC/ART/': new Uint8Array(), 'SRC/DIST/': new Uint8Array(), 'PASCAL/': new Uint8Array(), '.jsdos/': new Uint8Array() };
  let source = path.join(root, 'SRC');
  if (mode === 'classic') {
    const archive = path.join(work, 'main.tar');
    execFileSync('git', ['archive', '--format=tar', '-o', archive, 'main', 'SRC'], { cwd: root });
    const checkout = fs.mkdtempSync(path.join(work, 'classic-'));
    execFileSync('tar', ['-xf', archive, '-C', checkout]);
    source = path.join(checkout, 'SRC');
  }
  for (const [name, data] of Object.entries(files(source))) {
    if (/\.(pas|inc|pcx)$/i.test(name) || name.toUpperCase() === 'PACK.LST') input['SRC/' + name.toUpperCase()] = data;
  }
  for (const name of ['TPC.EXE', 'TURBO.TPL']) input['PASCAL/' + name] = fs.readFileSync(path.join(root, 'PASCAL', name));
  input['SRC/DIST/'] = new Uint8Array();
  const commands = 'cd SRC\n..\\PASCAL\\TPC.EXE KB2.PAS /B /L > GAME.LOG\n..\\PASCAL\\TPC.EXE RSPACK.PAS /B /L > PACKER.LOG\nRSPACK.EXE > PACK.LOG\necho BUILD_FINISHED\n';
  input['.jsdos/dosbox.conf'] = Buffer.from(conf(commands, true));
  const ci = await emulators.dosboxNode(zipSync(input));
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('DOS build timeout')), 120000);
    ci.events().onStdout(message => {
      if (message.includes('BUILD_FINISHED')) { clearTimeout(timer); resolve(); }
    });
  });
  const game = {};
  try {
    for (const name of ['GAME.LOG', 'PACKER.LOG', 'PACK.LOG']) {
      const log = Buffer.from(await ci.fsReadFile('SRC/' + name));
      fs.writeFileSync(path.join(work, mode + '-' + name), log);
      if (/Error \d|Fatal|Runtime error/i.test(log.toString())) throw new Error(`${mode}: ${name}: ${log}`);
    }
    game['KB2.EXE'] = await ci.fsReadFile('SRC/KB2.EXE');
    const tree = await ci.fsTree();
    const src = tree.nodes.find(n => n.name.toUpperCase() === 'SRC');
    const dist = src.nodes.find(n => n.name.toUpperCase() === 'DIST');
    for (const node of dist.nodes) if (/\.(pic|fnt)$/i.test(node.name)) game[node.name.toUpperCase()] = await ci.fsReadFile('SRC/DIST/' + node.name);
    if (Object.keys(game).length < 20) throw new Error('Missing game artwork');
    game['.jsdos/dosbox.conf'] = Buffer.from(conf('KB2.EXE\nexit'));
    fs.writeFileSync(path.join(out, 'games', mode + '.jsdos'), zipSync(game));
    return { source: mode === 'classic' ? execFileSync('git', ['rev-parse', 'main'], {cwd: root}).toString().trim() : 'working tree', exeSha256: require('node:crypto').createHash('sha256').update(game['KB2.EXE']).digest('hex') };
  } finally { await ci.exit(); }
}
(async () => {
  if (process.argv[2]) {
    const mode = process.argv[2];
    const result = await build(mode);
    fs.writeFileSync(path.join(work, mode + '.json'), JSON.stringify(result));
    return;
  }
  fs.copyFileSync(path.join(runtime, 'emulators.js'), path.join(out, 'vendor/emulators.js'));
  for (const name of ['wdosbox-x.js', 'wdosbox-x.wasm']) {
    const built = path.join(work, 'runtime', name);
    if (!fs.existsSync(built)) throw new Error('Сначала соберите ядро: WEB/runtime/build.sh (Emscripten 5.0.2).');
    fs.copyFileSync(built, path.join(out, 'vendor', name));
  }
  for (const name of ['fastlaunch.patch', 'fastlaunch-ega.patch', 'startup-cycles.patch', 'startup-keyboard.patch', 'startup-video.patch', 'build.sh', 'package.cjs']) fs.copyFileSync(path.join(__dirname, 'runtime', name), path.join(out, 'vendor', name));
  fs.copyFileSync(path.join(__dirname, 'node_modules/emulators/LICENSE'), path.join(out, 'vendor/LICENSE'));
  const builds = {};
  for (const mode of ['classic', 'continued']) {
    console.log('Building ' + mode);
    execFileSync(process.execPath, [__filename, mode], { stdio: 'inherit' });
    builds[mode] = JSON.parse(fs.readFileSync(path.join(work, mode + '.json')));
  }
  fs.writeFileSync(path.join(out, 'games/builds.json'), JSON.stringify(builds, null, 2));
  require('./prepare-page.cjs')();
  fs.writeFileSync(path.join(out, '.nojekyll'), '');
  console.log('Ready: WEB/dist');
})().catch(error => { console.error(error); process.exit(1); });
