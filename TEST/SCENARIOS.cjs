const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),vm=require('node:vm');
const {zipSync}=require('../WEB/node_modules/fflate');
const {scenarioStore}=require('../TOOLS/scenarios/store.cjs');
const {injectHtml,patchWorker}=require('../WEB/scenarios/server.cjs');
const snapshot=require('../TOOLS/scenarios/snapshot.cjs'),restore=require('../TOOLS/scenarios/restore.cjs');
const root=path.resolve(__dirname,'..'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'kb2-scenarios-'));
(async()=>{
try {
  const store=scenarioStore(root,temp);assert.deepEqual(store.list(),[]);
  const parts={};for(const name of ['CPU','Memory','Vga','Render','Dos','Keyboard','Pic','Mixer','DOSBox-X_Version','Program_Name'])parts[name]=Buffer.from('fixture '+name);
  const bytes=Buffer.from(zipSync(parts));
  const item={format:2,type:'dosbox-x-snapshot',title:'Карта уже куплена',exeSha256:'a'.repeat(64),assetsSha256:'b'.repeat(64),runtimeSha256:'c'.repeat(64),configSha256:'d'.repeat(64),snapshotSha256:snapshot.sha(bytes),snapshotBytes:bytes.length,frameSha256:'e'.repeat(64)};
  fs.writeFileSync(path.join(temp,'owned.sav'),bytes);fs.writeFileSync(path.join(temp,'owned.json'),JSON.stringify(item));
  assert.deepEqual(store.list(),[{id:'owned',title:item.title}]);assert.deepEqual(store.read('owned'),bytes);
  assert.throws(()=>store.get('../owned'));assert.throws(()=>scenarioStore(root,path.join(root,'states')));
  fs.writeFileSync(path.join(temp,'legacy.json'),JSON.stringify({format:1,campaign:'old',steps:[]}));assert.throws(()=>store.get('legacy'));assert.equal(store.list().length,1);
  const damaged=Buffer.from(bytes);damaged[100]^=1;fs.writeFileSync(path.join(temp,'owned.sav'),damaged);assert.throws(()=>store.read('owned'),/checksum/);
  assert.throws(()=>snapshot.validate(zipSync({CPU:Buffer.from('only CPU')})),/Incomplete/);
  assert.ok(injectHtml('<script src="app.js"></script>').includes('/__scenarios/client.js'));
  assert.throws(()=>patchWorker('changed runtime'));
  const source=fs.readFileSync(path.join(root,'WEB/runtime/vendor/wdosbox-x.js'),'utf8');assert.ok(patchWorker(source).includes('kb2-snapshot'));assert.ok(!source.includes('kb2-snapshot'));
  const archive=zipSync({'.jsdos/dosbox.conf':Buffer.from('[dosbox]\nmachine=ega\n'),'KB2.EXE':Buffer.from('EXE fixture')});
  const {unzipSync}=require('../WEB/node_modules/fflate'),local=unzipSync(snapshot.localBundle(archive));
  assert.equal(Buffer.from(local['KB2.EXE']).toString(),'EXE fixture');assert.ok(Buffer.from(local['.jsdos/dosbox.conf']).toString().includes('savefile='+snapshot.snapshotPath));

  // Native completion protocol has no guest-memory or keyboard API at all.
  const messages=[],closed=[];
  const originalClose=stream=>closed.push(stream.position),originalSend=(name,props)=>messages.push({name,props});
  let triggered;
  const Module={FS:{stat:()=>({size:123}),close:originalClose},sendMessage:originalSend,withString:(value,fn)=>fn(value),_TriggerEventByName:value=>triggered=value};
  restore({id:1,op:'restore'},Module);assert.equal(triggered,'hand_loadstate');
  Module.FS.close({path:snapshot.snapshotPath,position:0});Module.sendMessage('ws-update-lines',{lines:[]});assert.equal(messages.length,1);
  Module.FS.close({path:snapshot.snapshotPath,position:123});assert.equal(messages.length,1);
  Module.sendMessage('ws-update-lines',{lines:[]});
  const reply=JSON.parse(messages.at(-1).props.message);assert.deepEqual(reply,{id:1,result:{restored:true}});
  assert.equal(Module.FS.close,originalClose);assert.equal(Module.sendMessage,originalSend);assert.equal(Module.kb2SnapshotLoading,false);
  restore({id:2,op:'install'},Module);assert.match(JSON.parse(messages.at(-1).props.message).error,/Unknown/);

  // Exercise the real client loading method without a browser. Its only guest
  // operations must be writing the .sav file and requesting native restoration.
  const frame=Uint8Array.of(12,34,56),meta={snapshotBytes:bytes.length,snapshotSha256:snapshot.sha(bytes),frameSha256:snapshot.sha(frame)};
  const events={},calls=[],registered=[],focus=()=>{};
  const context={console,Uint8Array,TextDecoder,Map,Promise,JSON,Date,Error,Array,setTimeout,clearTimeout,crypto:require('node:crypto').webcrypto,
    EventSource:class{},ResizeObserver:class{observe(){}},window:{addEventListener:type=>registered.push(type)},
    document:{addEventListener(){},querySelector:selector=>selector==='#local-scenarios'?null:{focus}},
    fetch:async url=>({ok:true,json:async()=>url.endsWith('/list')?[]:meta,arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)})};
  vm.runInNewContext(fs.readFileSync(path.join(root,'WEB/scenarios/client.js'),'utf8'),context);
  const client=context.window.kb2LocalScenarios;client.render=()=>{};
  const pixels=Buffer.alloc(640*350*3,15),normalized=require('../TOOLS/scenarios/frame.cjs').normalize(pixels,['magic','wealth']);
  assert.deepEqual(Buffer.from(client.frameBytes(pixels,['magic','wealth'])),normalized,'Client and offline frame checks must mask the same animated pixels');
  assert.throws(()=>client.frameBytes(pixels,['unknown']),/Неизвестная/);
  const ci={events:()=>({onMessage:fn=>events.message=fn,onFrame:fn=>events.frame=fn}),
    fsWriteFile:async(file,data)=>{calls.push(['file',file]);assert.deepEqual(Buffer.from(data),bytes);},resume:()=>{},
    sendBackendEvent:event=>{calls.push(['event',event.type,event.op]);assert.equal(event.op,'restore');events.frame(frame,null);events.message('log','[kb2-snapshot]'+JSON.stringify({id:event.id,result:{restored:true}}));}};
  const run={ci,isCurrent:()=>true,isReady:()=>true,releaseKeys(){},restart:async()=>{calls.push(['restart']);client.attach(run);}};
  client.attach(run);await client.apply('owned');
  assert.equal(client.error,null);assert.equal(client.selected,'owned');assert.equal(run.capture,false);
  assert.deepEqual(calls,[['restart'],['file',snapshot.snapshotFile],['event','kb2-snapshot','restore']]);
  assert.ok(!registered.includes('keyup'));
  console.log('PASS: native snapshot store, integrity/legacy rejection, completion after restored frame, client loading without RAM writes or input replay.');
} finally {
  if(!path.resolve(temp).startsWith(path.join(path.resolve(os.tmpdir()),'kb2-scenarios-')))throw Error('Unexpected test cleanup path');
  fs.rmSync(temp,{recursive:true,force:true});
}
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
