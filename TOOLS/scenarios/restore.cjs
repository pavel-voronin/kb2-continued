// Full-snapshot completion bridge. No guest RAM access, campaign writes or keys.
module.exports=function restoreSnapshot(message,Module) {
  const reply=(result,error)=>Module.sendMessage('ws-log',{tag:'kb2-snapshot',message:JSON.stringify({id:message.id,result,error})});
  if(message.op!=='restore'){reply(null,'Unknown snapshot operation');return;}
  if(Module.kb2SnapshotLoading){reply(null,'Snapshot restoration is already running');return;}
  const file='/home/web_user/.jsdos/scenario.sav',originalClose=Module.FS.close,originalSend=Module.sendMessage;
  let timer,closed=false,finished=false;
  function cleanup(){clearTimeout(timer);Module.FS.close=originalClose;Module.sendMessage=originalSend;Module.kb2SnapshotLoading=false;}
  function done(error){if(finished)return;finished=true;cleanup();reply(error?null:{restored:true},error);}
  try {
    if(Module.FS.stat(file).size===0)throw Error('Empty emulator snapshot');
    Module.kb2SnapshotLoading=true;
    Module.FS.close=function(stream){
      // The preliminary ifstream existence check reads no bytes. The ZIP reader
      // closes after all native state components have been restored.
      const loaded=stream.path===file&&stream.position>0;
      const result=originalClose.call(this,stream);if(loaded)closed=true;return result;
    };
    Module.sendMessage=function(name,props,transfer){
      originalSend(name,props,transfer);
      if(closed&&name==='ws-update-lines')done();
    };
    timer=setTimeout(()=>done('No restored frame received from the emulator'),12000);
    Module.withString('hand_loadstate',pointer=>Module._TriggerEventByName(pointer));
  }catch(error){done(error.message);}
};
