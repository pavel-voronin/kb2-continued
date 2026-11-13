// Offline preparation/verification only. This module is never served to a browser.
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const snapshot=require('./snapshot.cjs'),restore=require('./restore.cjs');
const ROOT=path.resolve(__dirname,'../..');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function protectBootSleep(Module,ready){
  // The shipped Asyncify build cannot unwind device_CON::Write. Native DOS
  // shell initialization occasionally crosses its 24 ms yield threshold in
  // Node. Complete only that pre-KB2 boot synchronously; restore the unmodified
  // host scheduler as soon as the game enters its graphics mode.
  let hostSleep,wrapped;
  Object.defineProperty(Module,'sync_sleep',{configurable:true,get:()=>wrapped,set(fn){hostSleep=fn;wrapped=wakeUp=>ready()?hostSleep(wakeUp):wakeUp();}});
  return ()=>{Object.defineProperty(Module,'sync_sleep',{configurable:true,writable:true,value:hostSleep});};
}
async function wait(check,label,timeout=15000) {
  const deadline=Date.now()+timeout;
  while(Date.now()<deadline){if(check())return;await sleep(20);}
  throw Error('Timed out: '+label);
}
function sourceLayout(exe) {
  const result=spawnSync(process.env.PYTHON||'python',['-B',path.join(__dirname,'game-state.py'),exe],{encoding:'utf8',windowsHide:true});
  if(result.status!==0)throw Error(result.stderr||'Cannot inspect the compiled game layout');
  return JSON.parse(result.stdout);
}
class Headless {
  static async start(game,{base,baseBytes}={}) {
    // Keep the real mixer enabled and the same 44.1 kHz configuration. Only the
    // host audio sink is silent; no browser or audio device is opened by Node.
    globalThis.AudioContext=class {
      constructor(){this.sampleRate=44100;this.state='suspended';this.destination={};}
      createScriptProcessor(){return {connect(){},disconnect(){}};}
      createBuffer(channels,length){const data=Array.from({length:channels},()=>new Float32Array(length));return {getChannelData:index=>data[index]};}
      resume(){return Promise.resolve();}
    };
    const run=new Headless();
    // Finish synchronous source inspection before entering the native runtime.
    run.layout=sourceLayout(path.join(ROOT,'WEB/.build/dev/build/SRC/DIST/KB2.EXE'));
    const factory=require(path.join(ROOT,'WEB/runtime/vendor/wdosbox-x.js'));
    run.mod=await factory({noInitialRun:true,noExitRuntime:true,
      locateFile:name=>path.join(ROOT,'WEB/runtime/vendor',name),
      audioPort:{postMessage(message){if(message instanceof Float32Array)run.audioSamples+=message.length;}},
      postMessage:(name,props)=>run.message(name,props)});
    run.finishBootSleep=protectBootSleep(run.mod,()=>run.graphicsReady);
    run.mod.callMain(['kb2-snapshot']);
    run.mod.FS.mkdirTree('/home/web_user/.jsdos');run.mod.FS.chdir('/home/web_user');
    for(const [name,bytes] of Object.entries(game)){
      run.mod.FS.mkdirTree(path.posix.dirname('/home/web_user/'+name));
      run.mod.FS.writeFile(name,name==='.jsdos/dosbox.conf'?snapshot.config(bytes):bytes);
    }
    if(base)run.mod.FS.writeFile('KB2.DAT',fs.readFileSync(base));
    if(baseBytes)run.mod.FS.writeFile('KB2.DAT',baseBytes);
    run.font=Buffer.from(game['KB2.FNT'].slice(256,352));
    await new Promise(resolve=>setImmediate(resolve));
    run.trigger('startup_cycles:30000');run.send('wc-run');
    await wait(()=>run.startupReady&&run.findGame()&&run.frames>0,'normal game startup menu');
    return run;
  }
  constructor(){this.frames=0;this.rgb=null;this.width=0;this.height=0;this.audioSamples=0;this.errors=[];this.pending=new Map();this.serial=0;}
  send(name,props={}){this.mod.messageHandler({data:{name,props:{sessionId:'kb2-snapshot',...props}}});}
  trigger(event){this.send('wc-backend-event',{json:JSON.stringify({type:'wc-trigger-event',event})});}
  message(name,props) {
    if(name==='ws-sync-sleep')setImmediate(()=>this.send('wc-sync-sleep',props));
    else if(name==='ws-frame-set-size'){this.width=props.width;this.height=props.height;this.rgb=new Uint8Array(this.width*this.height*3);}
    else if(name==='ws-update-lines'){for(const line of props.lines)this.rgb.set(line.heapu8,line.start*this.width*3);this.frames++;}
    else if(name==='ws-err'){this.errors.push(props.message);if(process.env.KB2_SCENARIO_TRACE)console.error('[native error]',props.message);}
    else if(name==='ws-log'){
      if(process.env.KB2_SCENARIO_TRACE)console.log('[native log]',props.tag,props.message);
      if(props.tag==='kb2-startup'&&props.message==='graphics-init'){this.graphicsReady=true;this.finishBootSleep();}
      if(props.tag==='kb2-startup'&&props.message==='ready;cycles=3000')this.startupReady=true;
      if(props.tag==='kb2-snapshot'){
        const reply=JSON.parse(props.message),pending=this.pending.get(reply.id);
        if(pending){this.pending.delete(reply.id);if(reply.error)pending.reject(Error(reply.error));else pending.resolve(reply.result);}
      }
    }
  }
  findGame() {
    if(this.game!==undefined)return true;
    const h=Buffer.from(this.mod.HEAPU8.buffer),f=this.layout.fields;
    let at=-1;
    while((at=h.indexOf(Buffer.from([7,75,66,50,46,68,65,84]),at+1))>=0){
      if(!h.subarray(at+f['Runtime.Font'].offset+256,at+f['Runtime.Font'].offset+352).equals(this.font))continue;
      const p=h.readUInt32LE(at+f['Runtime.FontPointer'].offset),ram=at+f['Runtime.Font'].offset-((p>>>16)*16+(p&65535));
      if(ram<0||at-ram>=0xa0000||(at-ram-this.layout.gameDataOffset)%16)continue;
      this.game=at;this.ram=ram;return true;
    }
    return false;
  }
  field(name){const f=this.layout.fields[name];if(!f)throw Error('Unknown offline field: '+name);return Buffer.from(this.mod.HEAPU8.buffer,this.game+f.offset,f.size);}
  byte(name){return this.field(name)[0];}
  number(name){const field=this.field(name);return field.length===4?field.readInt32LE():field.length===2?field.readUInt16LE():field[0];}
  set(name,value){const f=this.field(name);if(f.length===4)f.writeInt32LE(value);else if(f.length===2)f.writeUInt16LE(value);else if(f.length===1)f[0]=value;else throw Error('Not a scalar: '+name);}
  position(name,x,y){this.field(name).set([x,y]);}
  map(x,y){return this.field('Campaign.Map')[(this.byte('Campaign.Island')-1)*4356+x*66+y];}
  setMap(x,y,tile){this.field('Campaign.Map')[(this.byte('Campaign.Island')-1)*4356+x*66+y]=tile;}
  key(scan,char=0){
    const view=new DataView(this.mod.HEAPU8.buffer),head=view.getUint16(this.ram+0x41a,true),tail=view.getUint16(this.ram+0x41c,true);
    if(head!==tail||tail<0x1e||tail>=0x3e)throw Error('Offline keyboard queue is not empty');
    view.setUint16(this.ram+0x400+tail,(scan<<8)|char,true);view.setUint16(this.ram+0x41c,tail===0x3c?0x1e:tail+2,true);
  }
  keyboardEmpty(){const view=new DataView(this.mod.HEAPU8.buffer);return view.getUint16(this.ram+0x41a,true)===view.getUint16(this.ram+0x41c,true);}
  seed(value){new DataView(this.mod.HEAPU8.buffer).setUint32(this.game+this.layout.seedDelta,value,true);}
  currentSeed(){return new DataView(this.mod.HEAPU8.buffer).getUint32(this.game+this.layout.seedDelta,true);}
  summary(){const island=this.byte('Campaign.Island');return {island,hero:[...this.field('Campaign.Hero')],wizard:[...this.field('World.WizardPosition')],gold:this.number('Campaign.Gold'),parts:this.byte('Campaign.MapParts'),owned:!!(this.field('Campaign.WizardVisited')[island-1]&2)};}
  frameHash(){return snapshot.sha(this.rgb);}
  async save(){
    if(this.mod.FS.analyzePath(snapshot.snapshotPath).exists)this.mod.FS.unlink(snapshot.snapshotPath);
    this.trigger('hand_savestate');
    await wait(()=>this.mod.FS.analyzePath(snapshot.snapshotPath).exists,'native snapshot write');
    const bytes=Buffer.from(this.mod.FS.readFile(snapshot.snapshotPath));snapshot.validate(bytes);return bytes;
  }
  async load(bytes){
    this.mod.FS.writeFile(snapshot.snapshotPath,bytes);
    const id=++this.serial;
    const result=new Promise((resolve,reject)=>this.pending.set(id,{resolve,reject}));
    restore({id,op:'restore'},this.mod);await result;
    // A snapshot restores DOS memory allocation too; resolve the cached address
    // again in the offline inspector, never in the browser loader.
    this.game=undefined;this.findGame();
  }
}
module.exports={Headless,wait,sleep,sourceLayout,ROOT,protectBootSleep};
