// Scenario metadata, integrity and discovery; independent of HTTP/UI.
const fs=require('node:fs'),path=require('node:path');
const snapshot=require('./snapshot.cjs');
function scenarioStore(root,requested) {
  const directory=snapshot.directory(root,requested);fs.mkdirSync(directory,{recursive:true});
  function get(id) {
    if(!/^[a-z0-9][a-z0-9-]{0,79}$/.test(id))throw Error('Invalid scenario ID');
    const file=path.join(directory,id+'.json');
    if(fs.statSync(file).size>16384)throw Error('Scenario metadata is too large');
    const data=JSON.parse(fs.readFileSync(file,'utf8'));
    if(data.format!==2||data.type!=='dosbox-x-snapshot'||typeof data.title!=='string'||!data.title.trim()||data.title.length>120||!Number.isSafeInteger(data.snapshotBytes)||data.snapshotBytes<=0||data.snapshotBytes>128*1024*1024)throw Error('Invalid full-snapshot scenario: '+id);
    for(const key of ['exeSha256','assetsSha256','runtimeSha256','configSha256','snapshotSha256','frameSha256'])if(!/^[a-f0-9]{64}$/.test(data[key]))throw Error('Missing snapshot fingerprint: '+key);
    require('./frame.cjs').validate(data.frameMask);
    if(fs.statSync(path.join(directory,id+'.sav')).size!==data.snapshotBytes)throw Error('Snapshot size mismatch: '+id);
    return data;
  }
  function read(id) {
    const data=get(id),bytes=fs.readFileSync(path.join(directory,id+'.sav'));
    if(snapshot.sha(bytes)!==data.snapshotSha256)throw Error('Snapshot checksum mismatch: '+id);
    snapshot.validate(bytes);return bytes;
  }
  function list() {
    return fs.readdirSync(directory).filter(name=>/^[a-z0-9][a-z0-9-]{0,79}\.json$/.test(name)).flatMap(name=>{
      const id=name.slice(0,-5);try{return [{id,title:get(id).title}];}catch{return [];}
    }).sort((a,b)=>a.title.localeCompare(b.title,'ru'));
  }
  return {directory,get,read,list};
}
module.exports={scenarioStore};
