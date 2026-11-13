// Local Vite extension. Snapshot files and metadata live outside the checkout.
const fs=require('node:fs'),path=require('node:path');
const snapshot=require('../../TOOLS/scenarios/snapshot.cjs'),restore=require('../../TOOLS/scenarios/restore.cjs');
const {scenarioStore}=require('../../TOOLS/scenarios/store.cjs');
function installScenarios(dev,{root,getGame}) {
  const store=scenarioStore(root),listeners=new Set();
  const watcher=fs.watch(store.directory,()=>{for(const res of listeners)res.write('data: changed\n\n');});
  dev.httpServer.once('close',()=>{watcher.close();for(const res of listeners)res.end();});
  dev.middlewares.use((req,res,next)=>{
    const url=new URL(req.url,'http://localhost');if(!url.pathname.startsWith('/__scenarios/'))return next();
    res.setHeader('Cache-Control','no-store');if(req.method!=='GET'){res.statusCode=405;return res.end();}
    if(url.pathname==='/__scenarios/events'){
      res.setHeader('Content-Type','text/event-stream');res.setHeader('Connection','keep-alive');res.write('data: connected\n\n');listeners.add(res);req.once('close',()=>listeners.delete(res));return;
    }
    try {
      if(url.pathname==='/__scenarios/client.js'||url.pathname==='/__scenarios/style.css'){
        const name=url.pathname.endsWith('.js')?'client.js':'style.css';res.setHeader('Content-Type',name.endsWith('.js')?'text/javascript':'text/css');return res.end(fs.readFileSync(path.join(__dirname,name)));
      }
      if(url.pathname==='/__scenarios/list'){res.setHeader('Content-Type','application/json');return res.end(JSON.stringify(store.list()));}
      const match=url.pathname.match(/^\/__scenarios\/(item|snapshot)\/([a-z0-9][a-z0-9-]{0,79})$/);
      if(!match){res.statusCode=404;return res.end();}
      const data=store.get(match[2]),current=snapshot.compatibility(root,getGame());
      for(const key of Object.keys(current))if(data[key]!==current[key]){res.statusCode=409;return res.end('Снимок подготовлен для другой сборки или настроек эмулятора. Подготовьте его заново.');}
      if(match[1]==='snapshot'){res.setHeader('Content-Type','application/octet-stream');return res.end(store.read(match[2]));}
      res.setHeader('Content-Type','application/json');res.end(JSON.stringify(data));
    }catch(error){res.statusCode=400;res.end(error.message);}
  });
  console.log('[scenarios] '+store.directory);
}
function patchWorker(source) {
  const needle='const message=JSON.parse(json);switch(message.type)';
  if(source.split(needle).length!==2)throw Error('Emulator snapshot hook no longer matches');
  return source.replace(needle,'const message=JSON.parse(json);if(message.type==="kb2-snapshot"){('+restore.toString()+')(message,Module);return;}switch(message.type)');
}
function injectHtml(html) {
  return html.replace('<script src="app.js','<link rel="stylesheet" href="/__scenarios/style.css">\n  <script src="/__scenarios/client.js" defer></script>\n  <script src="app.js');
}
module.exports={installScenarios,patchWorker,injectHtml,localBundle:snapshot.localBundle};
