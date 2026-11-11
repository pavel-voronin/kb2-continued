// Package the exact DOS release build; neither game nor emulator is compiled here.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {unzipSync} = require('fflate');
const gameBundle = require('./game-bundle.cjs');
const preparePage = require('./prepare-page.cjs');
const root = path.resolve(__dirname,'..');
const args = process.argv.slice(2);
function argument(name,fallback) {
  const i=args.indexOf(name);
  if(i<0)return fallback;
  if(!args[i+1] || args[i+1].startsWith('--'))throw new Error('Missing '+name);
  return args[i+1];
}
const tag=argument('--tag',process.env.RELEASE_TAG);
const gameDir=path.resolve(argument('--game-dir',path.join(root,'SRC/dist')));
const out=path.join(__dirname,'dist');
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const release=preparePage.readRelease(fs.readFileSync(path.join(root,'CHANGELOG.md'),'utf8'),tag);
const vendor=path.join(__dirname,'runtime/vendor');
const manifest=JSON.parse(fs.readFileSync(path.join(vendor,'manifest.json')));
for(const [name,hash] of Object.entries(manifest.files)) {
  if(sha(fs.readFileSync(path.join(vendor,name)))!==hash)throw new Error('Runtime checksum mismatch: '+name);
}
const classic=fs.readFileSync(path.join(__dirname,'assets/classic.jsdos'));
const classicExe=unzipSync(classic)['KB2.EXE'];
if(sha(classicExe)!=='c24025eb398a1c4a960b4ab7a21abb6fb81c86041f988178979381bfd8766a06')throw new Error('Classic EXE changed');
const {game,archive}=gameBundle(gameDir,classic);
// All input checks precede replacing the generated directory.
if(fs.existsSync(out) && fs.realpathSync(out)!==path.join(fs.realpathSync(__dirname),'dist'))throw new Error('Unexpected output directory');
fs.rmSync(out,{recursive:true,force:true});
fs.mkdirSync(path.join(out,'games'),{recursive:true});
fs.mkdirSync(path.join(out,'vendor'),{recursive:true});
fs.copyFileSync(path.join(__dirname,'assets/classic.jsdos'),path.join(out,'games/classic.jsdos'));
fs.writeFileSync(path.join(out,'games/continued.jsdos'),archive);
for(const name of Object.keys(manifest.files))fs.copyFileSync(path.join(vendor,name),path.join(out,'vendor',name));
fs.copyFileSync(path.join(vendor,'manifest.json'),path.join(out,'vendor/manifest.json'));
fs.cpSync(path.join(__dirname,'runtime/licenses'),path.join(out,'vendor/licenses'),{recursive:true});
for(const name of fs.readdirSync(path.join(__dirname,'runtime'))) {
  if(/\.(patch|sh|cjs|md)$/.test(name))fs.copyFileSync(path.join(__dirname,'runtime',name),path.join(out,'vendor',name));
}
const version={...release,tag:tag||null,commit:process.env.GITHUB_SHA||null,
  classicExeSha256:sha(classicExe),continuedExeSha256:sha(game['KB2.EXE']),runtime:manifest.revision};
fs.writeFileSync(path.join(out,'version.json'),JSON.stringify(version,null,2)+'\n');
fs.copyFileSync(path.join(root,'CHANGELOG.md'),path.join(out,'CHANGELOG.md'));
preparePage({tag});
console.log('Ready: WEB/dist — '+release.version);
