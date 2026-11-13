'use strict';
// Local UI: loads native snapshots, with no guest data editing or input replay.
window.kb2LocalScenarios=new class {
  constructor(){
    this.run=null;this.busy=false;this.serial=0;this.selected=null;
    this.events=new EventSource('/__scenarios/events');
    this.events.onmessage=()=>this.refresh();
    this.resize=new ResizeObserver(()=>this.position());this.resize.observe(document.querySelector('#player'));
    window.addEventListener('resize',()=>this.position());
    document.addEventListener('pointerdown',event=>{
      if(this.open&&!document.querySelector('#local-scenarios')?.contains(event.target))this.setOpen(false);
    });
    window.addEventListener('keydown',event=>{
      if(this.open&&event.code==='Escape'){event.preventDefault();event.stopImmediatePropagation();this.setOpen(false);}
      if(this.busy&&document.activeElement===document.querySelector('#screen')){event.preventDefault();event.stopImmediatePropagation();}
    },true);
    this.refresh();
  }
  attach(run){
    this.run=run;run.pending=new Map();
    run.ci.events().onFrame((rgb,rgba)=>{
      if(!run.capture)return;
      if(rgb)run.restoredFrame=new Uint8Array(rgb);
      else if(rgba){const bytes=new Uint8Array(rgba.length/4*3);for(let src=0,dst=0;src<rgba.length;src+=4){bytes[dst++]=rgba[src];bytes[dst++]=rgba[src+1];bytes[dst++]=rgba[src+2];}run.restoredFrame=bytes;}
    });
    run.ci.events().onMessage((type,message)=>{
      if(type!=='log'||!message.startsWith('[kb2-snapshot]'))return;
      const reply=JSON.parse(message.slice(14)),pending=run.pending.get(reply.id);
      if(!pending)return;run.pending.delete(reply.id);clearTimeout(pending.timer);
      if(reply.error)pending.reject(Error(reply.error));else pending.resolve(reply.result);
    });
  }
  discard(ci){
    // The bundled transport disposes its Worker and AudioPort in onExit(). A
    // scenario intentionally discards the guest instead of awaiting DOS shutdown.
    if(typeof ci.onExit!=='function')throw Error('Локальный загрузчик не поддерживает этот эмулятор.');
    ci.onExit();
  }
  request(op,data={}){
    const run=this.run,id=++this.serial;
    if(!run||!run.isCurrent())return Promise.reject(Error('Игра ещё запускается.'));
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{run.pending.delete(id);reject(Error('Эмулятор не ответил. Повторите выбор сценария.'));},15000);
      run.pending.set(id,{resolve,reject,timer});run.ci.sendBackendEvent({type:'kb2-snapshot',id,op,...data});
    });
  }
  async waitReady(){
    const until=Date.now()+30000;
    while(Date.now()<until){if(this.run?.isReady())return;await new Promise(resolve=>setTimeout(resolve,50));}
    throw Error('Дождитесь запуска игры.');
  }
  async hash(bytes){
    const hash=new Uint8Array(await crypto.subtle.digest('SHA-256',bytes));
    return Array.from(hash,b=>b.toString(16).padStart(2,'0')).join('');
  }
  frameBytes(bytes,masks=[]){
    if(!masks.length)return bytes;
    if(bytes.length!==640*350*3)throw Error('Неожиданный размер изображения эмулятора.');
    const rectangles={magic:[496,142,96,60],wealth:[496,202,96,60]},copy=new Uint8Array(bytes);
    for(const name of masks){const rect=rectangles[name];if(!rect)throw Error('Неизвестная анимация снимка.');const [x,y,w,h]=rect;for(let row=y;row<y+h;row++)copy.fill(0,(row*640+x)*3,(row*640+x+w)*3);}
    return copy;
  }
  async refresh(){
    try{
      const response=await fetch('/__scenarios/list');if(!response.ok)throw Error('Список сценариев недоступен.');
      this.items=await response.json();this.render();
    }catch(error){console.error(error);}
  }
  setOpen(open){
    this.open=open;this.run?.releaseKeys();
    if(this.run){if(open)this.run.ci.pause();else this.run.ci.resume();}
    this.render();
    if(open)document.querySelector('#local-scenario-close')?.focus({preventScroll:true});
    else document.querySelector('#screen').focus({preventScroll:true});
  }
  drawFrame(canvas){
    const ctx=canvas.getContext('2d',{alpha:false});
    if(!this.frameFont){
      const data=JSON.parse(document.querySelector('#release-data').textContent);
      this.frameFont=Uint8Array.from(atob(data.font),c=>c.charCodeAt(0));this.frameCodes=new Map();
      const decoder=new TextDecoder('ibm866');
      for(let code=0;code<240;code++)this.frameCodes.set(decoder.decode(Uint8Array.of(code)),code);
    }
    ctx.fillStyle='#000';ctx.fillRect(0,0,600,330);
    ctx.fillStyle='#fff';ctx.fillRect(4,3,593,323);
    ctx.fillStyle='#aaa';ctx.fillRect(6,5,589,319);
    ctx.fillStyle='#000';ctx.fillRect(8,7,585,315);
    ctx.fillStyle='#aaa';ctx.fillRect(8,28,585,2);
    const painter={context:ctx,font:this.frameFont,codes:this.frameCodes};
    ChangelogWindow.prototype.text.call(painter,'Сценарии',16,14);
    ChangelogWindow.prototype.text.call(painter,'[Закрыть]',504,14);
  }
  render(){
    let panel=document.querySelector('#local-scenarios');
    if(!this.items?.length){panel?.remove();return;}
    if(!panel){panel=document.createElement('aside');panel.id='local-scenarios';panel.setAttribute('aria-label','Сценарии');document.querySelector('#player').append(panel);}
    const toggle=document.createElement('button');toggle.id='local-scenario-toggle';toggle.title='Сценарии';toggle.setAttribute('aria-label','Сценарии');
    toggle.setAttribute('aria-expanded',String(!!this.open));toggle.setAttribute('aria-controls','local-scenario-menu');
    toggle.innerHTML='<svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="m8 2 6 3-6 3-6-3 6-3ZM2 8l6 3 6-3M2 11l6 3 6-3" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>';
    toggle.classList.toggle('loading',this.busy);
    toggle.addEventListener('click',()=>this.setOpen(!this.open));
    const menu=document.createElement('div');menu.id='local-scenario-menu';menu.hidden=!this.open;menu.setAttribute('role','dialog');menu.setAttribute('aria-label','Сценарии');
    const frame=document.createElement('canvas');frame.id='local-scenario-frame';frame.width=600;frame.height=330;frame.setAttribute('aria-hidden','true');this.drawFrame(frame);
    const close=document.createElement('button');close.id='local-scenario-close';close.setAttribute('aria-label','Закрыть сценарии');close.addEventListener('click',()=>this.setOpen(false));
    const content=document.createElement('div');content.id='local-scenario-content';
    const list=document.createElement('ul');
    for(const item of this.items){
      const li=document.createElement('li'),button=document.createElement('button');
      button.textContent=item.title;button.title=item.title;button.disabled=this.busy;button.setAttribute('aria-pressed',String(this.selected===item.id));
      button.classList.toggle('loading',this.busy&&this.loadingId===item.id);
      button.addEventListener('click',()=>this.apply(item.id));li.append(button);list.append(li);
    }
    const error=document.createElement('p');error.id='local-scenario-error';error.setAttribute('role','alert');error.hidden=!this.error;error.textContent=this.error||'';
    content.append(list,error);menu.append(frame,close,content);panel.replaceChildren(toggle,menu);panel.setAttribute('aria-busy',String(this.busy));panel.dataset.phase=this.phase||'';
    this.position();
  }
  position(){
    const panel=document.querySelector('#local-scenarios');if(!panel)return;
    const player=document.querySelector('#player').getBoundingClientRect(),screen=document.querySelector('#screen').getBoundingClientRect();
    const left=screen.right-player.left+2;
    panel.style.left=left+'px';
    panel.style.top=(screen.top-player.top+12)+'px';
    const menu=panel.querySelector('#local-scenario-menu');
    menu.style.left=(screen.left-player.left-left)+'px';menu.style.top='-12px';
    menu.style.width=screen.width+'px';menu.style.height=screen.height+'px';
    for(const button of menu.querySelectorAll('li button')){
      const size=14*screen.width/600;button.style.fontSize=size+'px';
      if(button.scrollWidth>button.clientWidth&&button.clientWidth>0)button.style.fontSize=(size*button.clientWidth/button.scrollWidth)+'px';
    }
  }
  async apply(id){
    if(this.busy)return;
    this.busy=true;this.loadingId=id;this.error=null;this.open=false;this.render();
    try{
      const response=await fetch('/__scenarios/item/'+encodeURIComponent(id));
      if(!response.ok)throw Error(await response.text());
      const scenario=await response.json();
      const fileResponse=await fetch('/__scenarios/snapshot/'+encodeURIComponent(id));
      if(!fileResponse.ok)throw Error(await fileResponse.text());
      const bytes=new Uint8Array(await fileResponse.arrayBuffer());
      if(bytes.length!==scenario.snapshotBytes||await this.hash(bytes)!==scenario.snapshotSha256)throw Error('Контрольная сумма снимка не совпала. Выберите сценарий заново.');
      await this.waitReady();
      const run=this.run;
      this.phase='restart';this.render();run.releaseKeys();await run.restart();
      await this.waitReady();
      this.phase='restore';this.render();
      await this.run.ci.fsWriteFile('.jsdos/scenario.sav',bytes);
      this.run.capture=true;
      await this.request('restore');
      if(!this.run.restoredFrame||await this.hash(this.frameBytes(this.run.restoredFrame,scenario.frameMask))!==scenario.frameSha256)throw Error('Эмулятор не восстановил изображение снимка целиком.');
      this.selected=id;
      this.phase='ready';
    }catch(error){this.error=error.message;this.open=true;console.error(error);}
    finally{if(this.run){this.run.capture=false;this.run.restoredFrame=null;this.run.ci.resume();}this.busy=false;this.render();document.querySelector('#screen').focus({preventScroll:true});}
  }
};
