// Shared by local serving and offline preparation. State bytes are native .sav files.
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),crypto=require('node:crypto');
const {zipSync,unzipSync}=require('fflate');
const snapshotFile='.jsdos/scenario.sav',snapshotPath='/home/web_user/'+snapshotFile;
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function directory(root,requested=process.env.KB2_SCENARIOS_DIR||path.join(process.env.LOCALAPPDATA||path.join(os.homedir(),'.local/share'),'kb2','scenarios')) {
  const target=path.resolve(requested),relative=path.relative(path.resolve(root),target);
  if(!relative||(!relative.startsWith('..'+path.sep)&&relative!=='..'&&!path.isAbsolute(relative)))throw Error('Scenario states must be outside the repository');
  return target;
}
function config(bytes) {
  const text=Buffer.from(bytes).toString('utf8');
  if(!text.startsWith('[dosbox]\n'))throw Error('Unexpected local DOS configuration');
  return Buffer.from(text.replace('[dosbox]\n','[dosbox]\nsavefile='+snapshotPath+'\nnoremark_savestate=true\n'));
}
function localBundle(archive) {
  const entries=unzipSync(archive);entries['.jsdos/dosbox.conf']=config(entries['.jsdos/dosbox.conf']);return zipSync(entries);
}
function compatibility(root,game) {
  const assets=crypto.createHash('sha256');
  for(const name of Object.keys(game).filter(n=>/\.(EXE|FNT|PIC)$/i.test(n)).sort()){assets.update(name+'\0');assets.update(game[name]);}
  return {exeSha256:sha(game['KB2.EXE']),assetsSha256:assets.digest('hex'),runtimeSha256:sha(fs.readFileSync(path.join(root,'WEB/runtime/vendor/wdosbox-x.wasm'))),configSha256:sha(config(game['.jsdos/dosbox.conf']))};
}
function validate(bytes) {
  const entries=unzipSync(bytes);
  for(const name of ['CPU','Memory','Vga','Render','Dos','Keyboard','Pic','Mixer','DOSBox-X_Version','Program_Name'])if(!entries[name])throw Error('Incomplete emulator snapshot: '+name);
  return entries;
}
module.exports={snapshotFile,snapshotPath,sha,directory,config,localBundle,compatibility,validate};
