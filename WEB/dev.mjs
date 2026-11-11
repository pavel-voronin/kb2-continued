import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
import {createServer} from 'vite';
import gameBundle from './game-bundle.cjs';
import page from './prepare-page.cjs';

const web=import.meta.dirname,root=path.dirname(web);
const sha=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const classic=fs.readFileSync(path.join(web,'assets/classic.jsdos'));
let current,server,timer,building=false,pending=false;
const sourceFile=file=>{
  const relative=path.relative(root,file).replaceAll('\\','/');
  return /^(BUILD\.BAT|PASCAL\/(TPC\.EXE|TURBO\.TPL)|SRC\/[^/]+\.(PAS|INC)|SRC\/PACK\.LST|SRC\/(ART|DOC)\/.*)$/i.test(relative);
};
function compile() {
  return new Promise((resolve,reject)=>{
    const child=spawn('pwsh',['-NoProfile','-File',path.join(web,'dev-game.ps1')],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe']});
    let output='';
    for(const stream of [child.stdout,child.stderr])stream.on('data',chunk=>{output+=chunk;process.stdout.write(chunk);});
    child.on('error',reject);
    child.on('exit',code=>code===0?resolve():reject(new Error(output||`DOS compiler exited: ${code}`)));
  });
}
async function rebuild() {
  if(building){pending=true;return;}
  building=true;
  try {
    console.log('[game] Compiling current sources...');
    await compile();
    const {archive,game}=gameBundle(path.join(web,'.build/dev/build/SRC/DIST'),classic);
    current={archive,game};
    console.log('[game] Ready: '+sha(game['KB2.EXE']));
    server?.ws.send({type:'full-reload',path:'*'});
  } catch(error) {
    console.error(error.message);
    if(!server)throw error;
    server.ws.send({type:'error',err:{message:error.message,stack:'',plugin:'kb2-dos-build'}});
  } finally {
    building=false;
    if(pending){pending=false;await rebuild();}
  }
}
await rebuild();
server=await createServer({
  root:web,configFile:false,publicDir:false,
  server:{host:'127.0.0.1',port:5173,strictPort:true,watch:{ignored:['**/.build/**','**/dist/**']},fs:{allow:[web]}},
  plugins:[{
    name:'kb2-local-game',
    transformIndexHtml:{order:'pre',handler(html){
      const markdown=fs.readFileSync(path.join(root,'CHANGELOG.md'),'utf8');
      const release=page.readRelease(markdown);
      const runtime=sha(Buffer.concat(['wdosbox-x.js','wdosbox-x.wasm'].map(name=>fs.readFileSync(path.join(web,'runtime/vendor',name))))).slice(0,16);
      const data=JSON.stringify({...release,markdown,bundles:{classic:sha(classic).slice(0,16),continued:sha(current.archive).slice(0,16)},runtime,font:Buffer.from(current.game['KB2.FNT']).toString('base64')}).replace(/</g,'\\u003c');
      // Vite treats ?v= as an immutable dependency URL; source files must stay unversioned in dev.
      return page.renderHtml(html,data,fs.readFileSync(path.join(web,'assets/startup.png')),'dev',runtime).replaceAll('?v=dev','');
    }},
    configureServer(dev){
      dev.watcher.add([path.join(root,'SRC'),path.join(root,'PASCAL'),path.join(root,'BUILD.BAT'),path.join(root,'CHANGELOG.md')]);
      dev.watcher.on('all',(event,file)=>{
        if(!['add','change','unlink'].includes(event)||!sourceFile(file))return;
        clearTimeout(timer);timer=setTimeout(()=>rebuild(),150);
      });
      dev.middlewares.use((req,res,next)=>{
        const url=new URL(req.url,'http://localhost').pathname;
        let bytes,type='application/octet-stream';
        if(url==='/games/continued.jsdos')bytes=current.archive;
        else if(url==='/games/classic.jsdos')bytes=classic;
        else if(url==='/version.json'){
          bytes=Buffer.from(JSON.stringify({local:true,continuedExeSha256:sha(current.game['KB2.EXE'])}));type='application/json';
        } else if(url.startsWith('/vendor/')) {
          const name=url.slice('/vendor/'.length);
          if(!/^[\w.-]+$/.test(name))return next();
          const file=path.join(web,'runtime/vendor',name);
          if(!fs.existsSync(file))return next();
          bytes=fs.readFileSync(file);
          if(name.endsWith('.js'))type='text/javascript';
          else if(name.endsWith('.wasm'))type='application/wasm';
          else if(name.endsWith('.json'))type='application/json';
        } else return next();
        res.setHeader('Content-Type',type);res.setHeader('Cache-Control','no-store');res.end(bytes);
      });
    },
    handleHotUpdate({file,server:dev}){
      if(sourceFile(file))return [];
      if(file.endsWith('.js')||file===path.join(root,'CHANGELOG.md')||file.endsWith('startup.png')){
        dev.ws.send({type:'full-reload',path:'*'});return [];
      }
    }
  }]
});
await server.listen();server.printUrls();server.bindCLIShortcuts({print:true});
