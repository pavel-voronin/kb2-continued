'use strict';
const $ = (selector) => document.querySelector(selector);
const player = $('#player'), canvas = $('#canvas'), screen = $('#screen');
const context = canvas.getContext('2d', { alpha: false });
// The EGA frame is 640×350; the original UI occupies its upper-left 600×330.
const viewWidth = 600, viewHeight = 330;
let frameWidth = 640, frameHeight = 350;
let ci, saveFiles, scale = 1, mode = 'continued', switching = false, ready = false;
let frameImage, bootTimer, soundEnabled = true;
const settingsKey = 'kb2.settings';
try {
  const saved = JSON.parse(localStorage.getItem(settingsKey));
  if(saved && typeof saved === 'object') {
    if(saved.mode === 'classic' || saved.mode === 'continued') mode = saved.mode;
    if(Number.isInteger(saved.percent) && saved.percent >= 100 && saved.percent <= 150 && saved.percent % 10 === 0) scale = saved.percent / 100;
    if(typeof saved.sound === 'boolean') soundEnabled = saved.sound;
  }
} catch { /* Unavailable storage or invalid settings: use defaults. */ }
function saveSettings() {
  try { localStorage.setItem(settingsKey, JSON.stringify({ mode, percent: Math.round(scale * 100), sound: soundEnabled })); }
  catch { /* The game remains usable when browser storage is disabled. */ }
}
const releaseData = JSON.parse($('#release-data').textContent);
const changelog = new ChangelogWindow({
  button: $('#release'), dialog: $('#changelog-dialog'), canvas: $('#changelog-canvas'),
  closeButton: $('#changelog-close'), data: releaseData,
  onOpen: () => { releaseKeys(); if(ci&&ready)ci.pause(); },
  onClose: () => { if(ci&&ready){ci.resume();applySound();} screen.focus({preventScroll:true}); }
});
changelog.setMode(mode);
const held = new Set();
const codes = { Escape:256, Enter:257, Tab:258, Backspace:259, Insert:260, Delete:261,
  ArrowRight:262, ArrowLeft:263, ArrowDown:264, ArrowUp:265, PageUp:266, PageDown:267,
  Home:268, End:269, CapsLock:280, ScrollLock:281, NumLock:282, PrintScreen:283,
  Pause:284, ShiftLeft:340, ControlLeft:341, AltLeft:342, ShiftRight:344, ControlRight:345,
  AltRight:346, Space:32, Minus:45, Equal:61, BracketLeft:91, BracketRight:93,
  Backslash:92, Semicolon:59, Quote:39, Backquote:96, Comma:44, Period:46, Slash:47,
  NumpadEnter:335, NumpadAdd:334, NumpadSubtract:333, NumpadMultiply:332, NumpadDivide:331,
  NumpadDecimal:330 };
for(let i=1;i<=12;i++) codes['F'+i]=289+i;
for(let i=0;i<=9;i++){codes['Digit'+i]=48+i;codes['Numpad'+i]=320+i;}
for(let i=65;i<=90;i++) codes['Key'+String.fromCharCode(i)]=i;
function releaseKeys(){if(ci) for(const code of held) ci.sendKeyEvent(code,false);held.clear();}
function send(code, down){if(!ci || !ready)return;if(down){if(held.has(code))return;held.add(code);}else held.delete(code);if(saveFiles)saveFiles.noteKey(code,down);ci.sendKeyEvent(code,down);}
function fit(){
  const full=!!document.fullscreenElement || document.body.classList.contains('browser-fullscreen');
  const viewport=$('#viewport');
  const ratio=full?Math.min(viewport.clientWidth/viewWidth,viewport.clientHeight/viewHeight):scale;
  screen.style.width=`${viewWidth*ratio}px`;screen.style.height=`${viewHeight*ratio}px`;
  // The artwork's visible frame spans x=4..596 inside the 600-pixel view.
  player.style.setProperty('--toolbar-width',`${593*ratio}px`);
  player.style.setProperty('--toolbar-offset',`${0.5*ratio}px`);
}
new ResizeObserver(fit).observe($('#viewport'));
for(let percent=100;percent<=150;percent+=10){
  const option=document.createElement('option');
  option.value=String(percent);option.textContent=percent+'%';option.selected=percent===Math.round(scale*100);
  $('#scale').append(option);
}
$('#scale').addEventListener('change',()=>{
  scale=Number($('#scale').value)/100;
  saveSettings();
  fit();screen.focus({preventScroll:true});
});
async function fullscreen(){try{releaseKeys();if(document.fullscreenElement)await document.exitFullscreen();else await player.requestFullscreen();screen.focus({preventScroll:true});}catch(error){$('#status').textContent='Полный экран недоступен: '+error.message;console.error(error);}}
$('#fullscreen').addEventListener('click',fullscreen);
document.addEventListener('fullscreenchange',()=>{releaseKeys();fit();$('#fullscreen').setAttribute('aria-label',document.fullscreenElement?'Выйти из полного экрана':'Развернуть');});
// If the browser reserves F11, its native fullscreen still uses our fit layout.
window.addEventListener('resize',()=>{
  document.body.classList.toggle('browser-fullscreen',!document.fullscreenElement && window.innerHeight>=window.screen.height-2);
  fit();
});
window.addEventListener('keydown',event=>{
  if(event.code==='F11'){event.preventDefault();if(!event.repeat)fullscreen();return;}
  if(event.code==='Escape'&&document.fullscreenElement){releaseKeys();return;}
  if(document.activeElement!==screen)return;
  const code=codes[event.code];if(code===undefined || event.metaKey)return;
  event.preventDefault();send(code,true);
});
window.addEventListener('keyup',event=>{const code=codes[event.code];if(held.has(code)){event.preventDefault();send(code,false);}});
screen.addEventListener('blur',releaseKeys);window.addEventListener('blur',releaseKeys);
document.addEventListener('visibilitychange',()=>{if(document.hidden)releaseKeys();});
screen.addEventListener('pointerdown',()=>screen.focus({preventScroll:true}));
function updateSoundButton(){
  $('#sound').textContent='Звук: '+(soundEnabled?'вкл.':'выкл.');$('#sound').setAttribute('aria-pressed',String(soundEnabled));
}
function applySound(){
  if(ci){if(soundEnabled)ci.unmute();else ci.mute();}
}
// js-dos owns the AudioContext, worklet, gesture handling and audio lifecycle.
$('#sound').addEventListener('click',()=>{
  soundEnabled=!soundEnabled;saveSettings();updateSoundButton();applySound();
  screen.focus({preventScroll:true});
});
async function start(nextMode){
  if(switching)return;switching=true;releaseKeys();ready=false;clearTimeout(bootTimer);
  screen.classList.remove('ready');$('#retry').hidden=true;$('#status').textContent='Загрузка…';
  $('#startup-screen').hidden=false;$('#loading').classList.remove('has-message');
  $('#mode').disabled=true;
  try{
    if(saveFiles){await saveFiles.dispose();saveFiles=null;}
    if(ci){await ci.exit();ci=null;}
    mode=nextMode;saveSettings();
    $('footer').replaceChildren(document.createTextNode('© 1992–1993 Сергей Прокофьев'));
    if(mode==='continued')$('footer').append(document.createElement('br'),document.createTextNode('© 2026 Павел Воронин'));
    changelog.setMode(mode);
    const response=await fetch(`games/${mode}.jsdos?v=${releaseData.bundles[mode]}`);if(!response.ok)throw new Error(`Загрузка игры: HTTP ${response.status}`);
    emulators.pathPrefix='vendor/';
    emulators.pathSuffix='?v='+releaseData.runtime;
    ci=await emulators.dosboxXWorker(new Uint8Array(await response.arrayBuffer()), {audioWorklet:true});
    applySound();
    const current=ci;
    let ended=false;
    function finishRun(){
      if(ci!==current || ended)return;
      ended=true;ready=false;releaseKeys();clearTimeout(bootTimer);screen.classList.remove('ready');
      $('#startup-screen').hidden=false;$('#retry').hidden=true;$('#loading').classList.remove('has-message');
      queueMicrotask(()=>{if(ci===current)start(mode);});
    }
    saveFiles=new SaveFilesClient({ci:current,isCurrent:()=>ci===current,onExit:finishRun});
    let programReady=false;
    let lastFrame;
    // The core restores 3000 cycles before KB2's first blocking keyboard read.
    ci.events().onMessage((type,message)=>{
      if(ci!==current || type!=='log' || message!=='[kb2-startup]ready;cycles=3000')return;
      programReady=true;
      if(lastFrame)paintFrame(...lastFrame);
    });
    ci.sendBackendEvent({type:'wc-trigger-event',event:'startup_cycles:30000'});
    bootTimer=setTimeout(()=>{if(!ready){$('#status').textContent='Игра не запустилась. Можно повторить запуск.';$('#retry').hidden=false;$('#loading').classList.add('has-message');}},30000);
    frameWidth=ci.width()||640;frameHeight=ci.height()||350;
    frameImage=context.createImageData(frameWidth,frameHeight);
    ci.events().onFrameSize((width,height)=>{frameWidth=width;frameHeight=height;frameImage=context.createImageData(width,height);});
    function paintFrame(rgb,rgba){
      if(ci!==current || ended)return;const data=rgb||rgba;if(!data)return;
      if(!ready){
        if(!programReady)return;
        let colored=0;const stride=rgb?3:4;
        for(let i=0;i<data.length;i+=stride)if(data[i]!==data[i+1]||data[i+1]!==data[i+2]){if(++colored>100)break;}
        if(colored<=100)return;
        ready=true;clearTimeout(bootTimer);screen.classList.add('ready');$('#startup-screen').hidden=true;if(changelog.open)current.pause();else screen.focus({preventScroll:true});
      }
      if(!frameImage||frameImage.data.length!==frameWidth*frameHeight*4)frameImage=context.createImageData(frameWidth,frameHeight);
      if(rgba)frameImage.data.set(rgba);else for(let src=0,dst=0;src<rgb.length;src+=3,dst+=4){frameImage.data[dst]=rgb[src];frameImage.data[dst+1]=rgb[src+1];frameImage.data[dst+2]=rgb[src+2];frameImage.data[dst+3]=255;}
      context.putImageData(frameImage,0,0);
    }
    ci.events().onFrame((rgb,rgba)=>{lastFrame=[rgb,rgba];paintFrame(rgb,rgba);});
    ci.events().onExit(finishRun);
  }catch(error){console.error(error);$('#status').textContent='Не удалось запустить игру: '+error.message;$('#retry').hidden=false;$('#loading').classList.add('has-message');}
  finally{switching=false;$('#mode').value=mode;$('#mode').disabled=false;}
}
$('#mode').addEventListener('change',()=>{if($('#mode').value!==mode)start($('#mode').value);});
$('#retry').addEventListener('click',()=>start(mode));
$('#mode').value=mode;
updateSoundButton();fit();player.classList.add('ui-ready');start(mode);
