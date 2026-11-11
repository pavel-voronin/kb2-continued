'use strict';
// Both DOS versions use the same fixed-size campaign format.
class SaveFilesClient {
  constructor({ci,isCurrent,onExit}) {
    this.ci=ci;this.isCurrent=isCurrent;this.onExit=onExit;
    this.closed=false;this.selecting=false;this.quickSave=false;
    this.downloads=Promise.resolve();
    this.input=document.createElement('input');
    this.input.type='file';this.input.accept='.kb2,.dat';this.input.hidden=true;
    document.body.append(this.input);
    this.input.addEventListener('cancel',()=>{this.selecting=false;this.focusGame();});
    this.input.addEventListener('change',()=>this.importFile());
    ci.events().onMessage((type,message)=>{
      if(this.closed || !isCurrent() || type!=='log' || !message.startsWith('[kb2-files]'))return;
      const action=message.slice(11);
      if(action==='load-request')this.chooseFile();
      else if(action==='game-exit')onExit();
      else if(action.startsWith('saved:')) {
        const file=action.slice(6).replace(/\\/g,'/').replace(/^C:\//i,'');
        const quick=file==='KB2.DAT' && this.quickSave;
        this.quickSave=false;
        if(quick || /\.KB2$/i.test(file))this.downloads=this.downloads.then(()=>this.download(file)).catch(error=>this.report(error));
      }
    });
    ci.sendBackendEvent({type:'wc-trigger-event',event:'kb2_files:1'});
  }
  noteKey(code,down) { if(down)this.quickSave=code===83; }
  focusGame() { if(!this.closed && this.isCurrent())document.querySelector('#screen').focus({preventScroll:true}); }
  report(error) { if(!this.closed && this.isCurrent()){window.alert(error.message);this.focusGame();} }
  chooseFile() {
    if(this.selecting)return;
    this.selecting=true;this.quickSave=false;this.input.value='';
    this.input.click();
  }
  async importFile() {
    try {
      const file=this.input.files[0];
      if(!file || this.closed || !this.isCurrent())return;
      if(file.size!==27729)throw new Error('Неверный размер сохранения. Ожидается файл KB2 на 27 729 байт.');
      const bytes=new Uint8Array(await file.arrayBuffer());
      if(this.closed || !this.isCurrent())return;
      await this.ci.fsWriteFile('WEBGAME.KB2',bytes);
      if(this.closed || !this.isCurrent())return;
      this.ci.sendBackendEvent({type:'wc-trigger-event',event:'kb2_load_ready'});
      this.ci.simulateKeyPress(257);
    } catch(error) { this.report(error); }
    finally { this.selecting=false;this.focusGame(); }
  }
  async download(file) {
    if(!this.isCurrent())return;
    if(file.startsWith('/') || file.split('/').includes('..'))throw new Error('Некорректное имя сохранения.');
    const bytes=await this.ci.fsReadFile(file);
    if(!this.isCurrent())return;
    if(bytes.length!==27729)throw new Error('Игра записала сохранение неполностью. Файл не выгружен.');
    const url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'}));
    const link=document.createElement('a');link.href=url;link.download=file.split('/').pop();
    document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  async dispose() { this.closed=true;this.input.remove();await this.downloads; }
}
