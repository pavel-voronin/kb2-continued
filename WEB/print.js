'use strict';
// The 9-pin ESC/P subset emitted by KB2. Coordinates are 1/60 inch horizontally
// and 1/72 inch vertically (Epson ESC K / ESC A), not screen pixels.
class EpsonPrintStream {
  constructor(){this.pending=new Uint8Array();this.reset();}
  reset(){this.x=0;this.y=0;this.spacing=12;this.wide=false;this.page={width:0,height:0,text:[],bands:[]};}
  push(bytes){
    const data=new Uint8Array(this.pending.length+bytes.length);
    data.set(this.pending);data.set(bytes,this.pending.length);
    const pages=[];
    const finish=()=>{if(this.page.width)pages.push(this.page);this.reset();};
    let at=0;
    while(at<data.length){
      const code=data[at];
      if(code===27){
        if(at+2>data.length)break;
        const command=data[at+1];
        if(command===65){
          if(at+3>data.length)break;
          this.spacing=data[at+2];at+=3;
        }else if(command===75){
          if(at+4>data.length)break;
          const length=data[at+2]+256*data[at+3];
          if(at+4+length>data.length)break;
          this.page.bands.push({x:this.x,y:this.y,bytes:data.slice(at+4,at+4+length)});
          this.x+=length;this.page.width=Math.max(this.page.width,this.x);
          this.page.height=Math.max(this.page.height,this.y+8);at+=4+length;
        }else throw new Error('Неизвестная команда принтера: ESC '+String.fromCharCode(command));
        continue;
      }
      at++;
      // Each KB2 request starts with BEL. Separate rapid F5 requests even when
      // they arrive before DOSBox-X's idle form feed. BEL inside ESC K is data.
      if(code===7||code===12)finish();
      else if(code===14)this.wide=true;
      else if(code===20)this.wide=false;
      else if(code===13)this.x=0;
      else if(code===10){this.y+=this.spacing;this.wide=false;}
      else if(code>=32){
        const width=this.wide?12:6;
        this.page.text.push({x:this.x,y:this.y,width,code});
        this.x+=width;this.page.width=Math.max(this.page.width,this.x);
        this.page.height=Math.max(this.page.height,this.y+12);
      }else throw new Error('Неизвестный управляющий код принтера: '+code);
    }
    this.pending=data.slice(at);return pages;
  }
}

function printPageSvg(page){
  const escape=text=>text.replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const decoder=new TextDecoder('ibm866');
  const title=decoder.decode(Uint8Array.from(page.text,item=>item.code));
  const paths=[];
  for(const band of page.bands)for(let row=0;row<8;row++){
    const bit=128>>row;
    for(let x=0;x<band.bytes.length;){
      if(!(band.bytes[x]&bit)){x++;continue;}
      const start=x;while(x<band.bytes.length&&(band.bytes[x]&bit))x++;
      paths.push(`M${band.x+start} ${band.y+row}h${x-start}v1h-${x-start}z`);
    }
  }
  const text=page.text.map(item=>`<text x="${item.x*1.2}" y="${item.y+10}" textLength="${item.width*1.2}" lengthAdjust="spacingAndGlyphs">${escape(decoder.decode(Uint8Array.of(item.code)))}</text>`).join('');
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${page.width*1.2} ${page.height}" style="width:${page.width/60*25.4}mm;max-width:100%;height:auto" role="img" aria-label="${escape(title)}"><title>${escape(title)}</title><g font-family="monospace" font-size="12" fill="black">${text}</g><path transform="scale(1.2 1)" fill="black" shape-rendering="crispEdges" d="${paths.join('')}"/></svg>`;
  return {title,svg};
}

class PrintClient {
  constructor({ci,isCurrent,onOpen,onClose}){
    this.ci=ci;this.isCurrent=isCurrent;this.onOpen=onOpen;this.onClose=onClose;
    this.closed=false;this.offset=0;this.stream=new EpsonPrintStream();this.pages=[];
    this.poll();
  }
  async poll(){
    try{
      const tree=await this.ci.fsTree();
      if(this.closed||!this.isCurrent())return;
      const size=tree.nodes?.find(node=>node.name==='.jsdos')?.nodes?.find(node=>node.name==='print.prn')?.size||0;
      if(size<this.offset){this.offset=0;this.stream=new EpsonPrintStream();}
      if(size>this.offset){
        const bytes=await this.ci.fsReadFile('.jsdos/print.prn');
        if(this.closed||!this.isCurrent())return;
        this.pages.push(...this.stream.push(bytes.subarray(this.offset)));this.offset=bytes.length;
        this.printNext();
      }
    }catch(error){
      if(!this.closed&&this.isCurrent()){
        this.dispose();window.alert('Не удалось подготовить печать: '+error.message);
      }
    }finally{
      if(!this.closed&&this.isCurrent())this.timer=setTimeout(()=>this.poll(),400);
    }
  }
  printNext(){
    if(this.closed||!this.isCurrent()||this.frame||!this.pages.length)return;
    const {title,svg}=printPageSvg(this.pages.shift());
    const frame=document.createElement('iframe');this.frame=frame;
    frame.title='Печать карты';
    frame.style.cssText='position:fixed;left:0;top:0;width:1px;height:1px;opacity:0;pointer-events:none;border:0';
    this.onOpen();
    frame.addEventListener('load',async()=>{
      if(this.closed||this.frame!==frame)return;
      const view=frame.contentWindow;
      frame.contentDocument.title='Карта — '+title;
      view.addEventListener('afterprint',()=>this.finish(frame),{once:true});
      try{
        await frame.contentDocument.fonts.ready;
        if(this.closed||this.frame!==frame)return;
        view.focus();view.print();
      }catch(error){this.finish(frame);window.alert('Не удалось открыть печать: '+error.message);}
    },{once:true});
    // Only the decoded printer output is placed in the printable document.
    frame.srcdoc='<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>Карта</title><style>@page{size:A4 portrait;margin:10mm}html,body{margin:0;background:white;color:black}svg{display:block;break-inside:avoid}</style></head><body>'+svg+'</body></html>';
    document.body.append(frame);
  }
  finish(frame){
    if(this.frame!==frame)return;
    frame.remove();this.frame=null;
    if(this.isCurrent())this.onClose();
    if(!this.closed)queueMicrotask(()=>this.printNext());
  }
  dispose(){this.closed=true;clearTimeout(this.timer);this.pages=[];if(this.frame)this.finish(this.frame);}
}
if(typeof module!=='undefined')module.exports={EpsonPrintStream,printPageSvg};
