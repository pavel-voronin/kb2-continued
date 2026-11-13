// CLI and reusable offline assembly. The browser receives only the final .sav.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{spawnSync}=require('node:child_process');
const {Headless,wait,sleep,sourceLayout,ROOT}=require('./headless.cjs'),semantic=require('./semantic.cjs'),snapshot=require('./snapshot.cjs');
const bundle=require('../../WEB/game-bundle.cjs');
const frame=require('./frame.cjs');
function game(){return bundle(path.join(ROOT,'WEB/.build/dev/build/SRC/DIST'),fs.readFileSync(path.join(ROOT,'WEB/assets/classic.jsdos'))).game;}
const args=process.argv.slice(2);
const trace=(...values)=>{if(process.env.KB2_SCENARIO_TRACE)console.log('[assemble]',...values);};
function arg(name,fallback){const i=args.indexOf(name);if(i<0)return fallback;if(!args[i+1]||args[i+1].startsWith('--'))throw Error('Missing '+name);return args[i+1];}
function campaign(run){return Buffer.from(run.field('Campaign'));}
function campaignHash(run,view){const bytes=campaign(run);if(['world','near'].includes(view.kind))bytes[run.layout.campaign.fields.MagicPower.offset]=run.byte('Runtime.ActionScratch');return snapshot.sha(bytes);}
function cleanBase(run){
  const state=new semantic.State(run.layout,campaign(run));
  for(let land=1;land<=5;land++)for(let x=0;x<66;x++)for(let y=0;y<66;y++)if([12,28].includes(state.get('Map.'+land+'.'+x+'.'+y)))state.put('Map.'+land+'.'+x+'.'+y,0);
  state.put('ArchivedIsland',state.get('Island'));state.put('ArchiveMarker',0);
  return semantic.encode(run.layout,state.bytes);
}
async function initialize(directory,base){
  const run=await Headless.start(game());
  if(base&&path.extname(base).toLowerCase()==='.sav')await run.load(fs.readFileSync(base));
  else {
    // First-time world generation is cached; it is never repeated per scenario.
    run.seed(36);run.key(28,13);await wait(()=>run.keyboardEmpty(),'difficulty menu');run.key(28,13);
    await wait(()=>run.byte('Runtime.IdleCounter')>0&&run.byte('Campaign.Island')>0,'initial world generation',60000);
  }
  fs.mkdirSync(path.join(directory,'.cache'),{recursive:true});const file=path.join(directory,'.cache/base.dat');fs.writeFileSync(file,cleanBase(run));
  fs.writeFileSync(file+'.json',JSON.stringify({exeSha256:snapshot.sha(game()['KB2.EXE'])}));console.log('BASE',file);
}
async function press(run,scan,char=0,world=false,seed=36){
  if(world){run.set('Runtime.IdleCounter',0);run.set('World.WizardAge',0);run.set('World.MageAge',0);}
  run.seed(seed);const frames=run.frames;run.key(scan,char);
  await wait(()=>run.keyboardEmpty(),'native key consumed');
  await wait(()=>run.frames>frames,'native display updated');
  if(world)await wait(()=>run.byte('Runtime.IdleCounter')>0,'world input ready');
}
function locate(run,plan){
  if(!plan.near)return null;
  const kind=plan.near.kind,land=run.byte('Campaign.Island');let position;
  if(kind==='wizard'||kind==='mage')position=[...run.field('World.'+(kind==='wizard'?'Wizard':'Mage')+'Position')];
  else if(kind==='ritualStone')position=[...run.field('Campaign.RitualStonePosition')];
  else {
    const fields={town:['Towns',1],castle:['Castles',1],dwelling:['Dwellings',0],army:['WanderingArmies',0],underground:['Underground',1]};
    if(fields[kind]){const [name,lo]=fields[kind],slot=plan.near.slot??lo,state=new semantic.State(run.layout,campaign(run)),p=name+'.'+land+'.'+slot;position=[state.get(p+'.X'),state.get(p+'.Y')];}
    else {const tile=semantic.targets[kind];for(let x=3;x<=62&&!position;x++)for(let y=3;y<=62;y++)if(run.map(x,y)===tile){position=[x,y];break;}}
  }
  if(!position||position.some(n=>n<3||n>62))throw Error('No valid '+kind+' target');
  // Prefer the existing world geometry. A roamer can be moved to the nearest
  // suitable natural grass pair, so its seeded northward step stays blocked.
  const directions=[[0,1,72],[1,0,75],[-1,0,77],[0,-1,80],[1,1,71],[-1,1,73],[1,-1,79],[-1,-1,81]],candidates=[];
  if(kind==='wizard'||kind==='mage'){
    const random=require('./random.cjs'),choice=random.wizard(plan.seed),step=[[-1,-1],[0,-1],[1,-1],[1,0],[1,1],[0,1],[-1,1],[-1,0]][kind==='wizard'?choice.direction:choice.mageDirection];
    const old=position,hero=run.summary().hero;
    for(let x=4;x<=61;x++)for(let y=4;y<=61;y++)if(run.map(x,y)===0&&run.map(x+step[0],y+step[1])!==0){for(const [dx,dy,scan]of directions){const hx=x+dx,hy=y+dy;if(run.map(hx,hy)===0)candidates.push({position:[x,y],hero:[hx,hy],scan,d:Math.abs(hero[0]-hx)+Math.abs(hero[1]-hy)});}}
    candidates.sort((a,b)=>a.d-b.d);if(!candidates.length)throw Error('No safe roamer location');const picked=candidates[0];run.setMap(...old,0);run.setMap(...picked.position,semantic.targets[kind]);run.position('World.'+(kind==='wizard'?'Wizard':'Mage')+'Position',...picked.position);position=picked.position;
  }else for(const [dx,dy,scan]of directions){const x=position[0]+dx,y=position[1]+dy;if(x>=2&&x<=63&&y>=2&&y<=63&&[0,4].includes(run.map(x,y))&&(kind!=='castle'||dy>=0))candidates.push({hero:[x,y],position,scan,d:0});}
  const picked=candidates[0];if(!picked)throw Error('No walkable cell next to '+kind);run.position('Campaign.Hero',...picked.hero);return picked;
}
async function capture(file,base,specFile){
  const spec=JSON.parse(fs.readFileSync(specFile,'utf8')),layout=sourceLayout(path.join(ROOT,'WEB/.build/dev/build/SRC/DIST/KB2.EXE'));
  assert.deepEqual(semantic.coverage(layout).uncovered,[],'Every named campaign field needs semantic coverage');
  const plan=semantic.compile(layout,semantic.decode(layout,fs.readFileSync(base)),spec);
  const run=await Headless.start(game(),{baseBytes:semantic.encode(layout,plan.state.bytes)});
  trace('started');
  run.seed(plan.seed);run.key(80);await wait(()=>run.keyboardEmpty(),'continue selected');run.key(28,13);
  await wait(()=>run.byte('Runtime.IdleCounter')>0&&run.byte('Campaign.Island')>0,'semantic campaign loaded');
  trace('campaign loaded');
  // Native startup has now populated artwork and caches. Reinstate requested
  // campaign data it normalizes (discovery, heading, map markers), retaining
  // the generated roamer positions with matching map records.
  run.field('Campaign').set(plan.state.bytes);
  for(const [name,tile]of [['Wizard',12],['Mage',28]]){const position=[...run.field('World.'+name+'Position')];if(run.map(...position)!==0)throw Error('Generated roamer collides with requested terrain');run.setMap(...position,tile);}
  run.set('Runtime.ActionScratch',plan.state.get('MagicPower'));
  for(const [field,bytes]of Object.entries(plan.live))run.field(field).set(bytes);
  const aboard=run.byte('Runtime.ShipAbandonBlocked');
  if(!plan.state.get('Flags.Heading'))require('./art.cjs').mirrorTile(run,aboard?15:6);
  if(!plan.state.get('ShipHeading'))require('./art.cjs').mirrorTile(run,aboard?6:15);
  const encounter=locate(run,plan);
  trace('location',JSON.stringify(encounter));
  const gold=run.number('Campaign.Gold'),days=run.byte('Campaign.Days'),extra=run.number('Campaign.ExtraDays'),grace=run.byte('Campaign.EnemyGrace');
  // F10 then N returns through the native full world redraw without moving
  // hero or nearby armies. Compensate its calendar tick before issuing it.
  // No temporary terrain remains in the screenshot or underlying world.
  run.set('Campaign.ExtraDays',extra+1);
  run.set('Campaign.EnemyGrace',255);
  const hero=[...run.field('Campaign.Hero')];
  run.set('Runtime.IdleCounter',0);await press(run,68,0,false,plan.seed);await press(run,49,110);await wait(()=>run.byte('Runtime.IdleCounter')>0,'world redrawn');
  run.set('Campaign.Days',days);run.set('Campaign.ExtraDays',extra);run.set('Campaign.EnemyGrace',grace);
  assert.deepEqual([...run.field('Campaign.Hero')],hero,'Redraw must not move the hero');assert.equal(run.number('Campaign.Gold'),gold);
  trace('world redraw completed');
  if(plan.view.kind==='dialog'||plan.view.kind==='battle'){
    let encounterArmy;
    if(plan.view.kind==='battle'&&['army','guardian'].includes(plan.near.kind)){
      const state=new semantic.State(run.layout,campaign(run)),[species,counts]=semantic.enemyPaths(plan.near.kind,state.get('Island'),plan.near.slot);
      const active=Array.from({length:5},(_,i)=>i).filter(i=>state.get(species+'.'+i)<30);
      if(active.length===0)throw Error('Battle requires an enemy army');
      if(active.length===1){
        // ArmyReport treats a single stack as a joining offer. Stage a second
        // stack only while opening its prompt, restore the requested roster
        // before Battle initializes any native units or artwork.
        const slot=active[0]===0?1:0;encounterArmy=[species,counts].map(p=>{const {node,offset}=state.node(p);return {offset,bytes:Buffer.from(state.bytes.subarray(offset,offset+node.size))};});state.put(species+'.'+slot,state.get(species+'.'+active[0]));state.put(counts+'.'+slot,1);run.field('Campaign').set(state.bytes);
      }
    }
    run.set('Runtime.IdleCounter',0);run.set('World.WizardAge',0);run.set('World.MageAge',0);run.seed(plan.seed);
    run.key(encounter.scan);await wait(()=>run.keyboardEmpty(),'encounter input');await sleep(100);
    trace('encounter entered');
    if(plan.view.offer)assert.equal(run.currentSeed(),require('./random.cjs').wizard(plan.seed).seed,'Wizard must show the requested offer');
    if(plan.view.kind==='battle'){
      if(encounterArmy)for(const {offset,bytes}of encounterArmy)run.field('Campaign').set(bytes,offset);
      await press(run,21,121);await wait(()=>run.field('Runtime.BattleField').some(n=>n>=112&&n<=124)&&run.field('Runtime.BattleField').some(n=>n>=32&&n<=44),'native battle initialized');await sleep(100);
      trace('battle initialized');
      if(spec.battle&&Object.keys(spec.battle).some(k=>k!=='enemies'))await require('./combat.cjs').configure(run,spec.battle,press);
    }
    if(plan.view.section){const key=semantic.sections[plan.near.kind]?.[plan.view.section];if(!key)throw Error('Unknown encounter section');if(key.length)await press(run,...key);await sleep(80);}
    if(plan.near.kind==='town'&&plan.view.section==='goods'&&['GoodsStock','GoodsBuyPrices','GoodsSellPrices'].some(name=>plan.live['Runtime.'+name])){
      // Let the native shop initialize default prices first, then replace only
      // requested values and reopen its cached table for a consistent image.
      await press(run,1,27);
      for(const name of ['GoodsStock','GoodsBuyPrices','GoodsSellPrices'])if(plan.live['Runtime.'+name])run.field('Runtime.'+name).set(plan.live['Runtime.'+name]);
      await press(run,8,55);
    }
    const idle=run.byte('Runtime.IdleCounter');await sleep(80);
    assert.equal(run.byte('Runtime.IdleCounter'),idle,'Requested encounter must remain open, not return to the world input loop');
  }else if(plan.view.kind==='report'){await press(run,semantic.reports[plan.view.report]);await sleep(80);}
  const expected=run.summary(),bytes=await run.save();
  // The host's previous RGB update can precede the native save by part of a
  // frame (animated HUD/cursor). Fingerprint the saved image through the same
  // restore boundary used by the client, rather than an earlier host frame.
  await run.load(bytes);
  const frameMask=['world','near'].includes(plan.view.kind)?['magic',...(gold>999999?['wealth']:[])]:[];
  const frameSha256=snapshot.sha(frame.normalize(run.rgb,frameMask));
  fs.writeFileSync(file+'.rgb',run.rgb);
  const stateHash=campaignHash(run,plan.view),live=Object.fromEntries([...Object.keys(plan.live),'Campaign.Army','Campaign.Scrolls'].map(name=>[name,run.field(name).toString('hex')]));
  let battle;
  if(plan.view.kind==='battle'){const {base,state}=require('./combat.cjs').bind(run);battle={address:base-run.ram,bytes:state.bytes.toString('hex'),field:run.field('Runtime.BattleField').toString('hex'),counts:run.field('Runtime.BattleDistances').toString('hex')};}
  fs.writeFileSync(file,bytes);fs.writeFileSync(file+'.receipt',JSON.stringify({expected,frameSha256,frameMask,stateHash,live,battle,view:plan.view,near:plan.near,elapsed:Date.now()-Number(process.env.KB2_ASSEMBLE_STARTED||Date.now())}));
  console.log('CAPTURED',spec.id,JSON.stringify({bytes:bytes.length,state:expected}));
}
function verifyFrame(run,file,receipt,label){
  if(snapshot.sha(frame.normalize(run.rgb,receipt.frameMask))===receipt.frameSha256)return;
  const expected=fs.readFileSync(file+'.rgb');let minX=run.width,minY=run.height,maxX=0,maxY=0,n=0;for(let i=0;i<expected.length;i++)if(expected[i]!==run.rgb[i]){const pixel=Math.floor(i/3),x=pixel%run.width,y=Math.floor(pixel/run.width);minX=Math.min(x,minX);minY=Math.min(y,minY);maxX=Math.max(x,maxX);maxY=Math.max(y,maxY);n++;}throw Error(label+' frame differs: '+JSON.stringify({n,minX,minY,maxX,maxY}));
}
async function verify(file){
  const receipt=JSON.parse(fs.readFileSync(file+'.receipt','utf8')),bytes=fs.readFileSync(file),run=await Headless.start(game());await run.load(bytes);
  assert.deepEqual(run.summary(),receipt.expected);
  assert.equal(campaignHash(run,receipt.view),receipt.stateHash,'All campaign bytes restore (logical magic power excludes idle animation)');
  verifyFrame(run,file,receipt,'Cold restore');
  for(const [field,value]of Object.entries(receipt.live))assert.equal(run.field(field).toString('hex'),value,'Cold restore '+field);
  if(receipt.battle){assert.equal(run.field('Runtime.BattleField').toString('hex'),receipt.battle.field);assert.equal(run.field('Runtime.BattleDistances').toString('hex'),receipt.battle.counts);const bytes=Buffer.from(run.mod.HEAPU8.buffer,run.ram+receipt.battle.address,receipt.battle.bytes.length/2);assert.equal(bytes.toString('hex'),receipt.battle.bytes,'Complete combat stack restored');}
  if(receipt.view.offer==='ancientMap'&&receipt.expected.owned){const before=run.summary();await press(run,7,54,true);assert.equal(run.number('Campaign.Gold'),before.gold);assert.equal(run.byte('Campaign.MapParts'),before.parts);for(let i=0;i<4;i++){const hero=run.summary().hero,step=[[0,1,80],[1,0,77],[-1,0,75],[0,-1,72]].find(([dx,dy])=>run.map(hero[0]+dx,hero[1]+dy)===0);if(!step)throw Error('No safe movement after wizard dialog');await press(run,step[2],0,true);assert.deepEqual(run.summary().hero,[hero[0]+step[0],hero[1]+step[1]]);}}
  else if(receipt.view.kind==='battle'){const frame=run.frames;run.key(77);await wait(()=>run.keyboardEmpty()&&run.frames>frame,'battle continues after restore');assert.equal(run.byte('Runtime.BattleResult'),0);}
  else if(receipt.view.kind==='world'||receipt.view.kind==='near'){const hero=run.summary().hero,step=[[0,1,80],[1,0,77],[-1,0,75],[0,-1,72]].find(([dx,dy])=>run.map(hero[0]+dx,hero[1]+dy)===0);if(!step)throw Error('World scenario has no walkable exit');await press(run,step[2],0,true);assert.deepEqual(run.summary().hero,[hero[0]+step[0],hero[1]+step[1]]);}
  else {await press(run,1,27);}
  await run.load(bytes);assert.deepEqual(run.summary(),receipt.expected);assert.equal(campaignHash(run,receipt.view),receipt.stateHash,'All campaign bytes restore again');verifyFrame(run,file,receipt,'Repeated restore');assert.deepEqual(run.errors,[]);
  console.log('VERIFIED',JSON.stringify({coldRestore:true,reload:true,continues:true,frame:true,animatedHud:receipt.frameMask}));
}
function child(mode,options){const result=spawnSync(process.execPath,[__filename,mode,...Object.entries(options).filter(([,v])=>v!==undefined).flatMap(([k,v])=>['--'+k,v])],{encoding:'utf8',windowsHide:true,timeout:90000,maxBuffer:4*1024*1024});if(result.stdout)process.stdout.write(result.stdout);if(result.status!==0)throw Error(result.stderr||result.error?.message||'Assembly failed');}
async function main(){
  const directory=snapshot.directory(ROOT,arg('--directory')),output=arg('--output');fs.mkdirSync(directory,{recursive:true});
  if(args.includes('--capture'))return capture(output,arg('--base'),arg('--spec'));
  if(args.includes('--verify'))return verify(output);
  if(args.includes('--init'))return initialize(directory,arg('--base'));
  if(args.includes('--catalog')){const layout=sourceLayout(path.join(ROOT,'WEB/.build/dev/build/SRC/DIST/KB2.EXE'));console.log(JSON.stringify({version:1,...semantic.coverage(layout),groups:semantic.groups,flags:semantic.flags,creatures:layout.creatures,catalogs:layout.catalogs,tiles:semantic.tiles,targets:semantic.targets,reports:semantic.reports,sections:semantic.sections,wizardOffers:require('./random.cjs').offers,live:{runtime:semantic.runtime,roamers:semantic.worldRuntime},combat:{fields:require('./combat.cjs').allowed,unitFields:require('./combat.cjs').units,schema:layout.battle},schema:layout.campaign},null,2));return;}
  const started=Date.now(),specFile=arg('--spec');if(!specFile)throw Error('Pass --spec <external scenario.json>; --catalog lists semantic fields');
  const spec=JSON.parse(fs.readFileSync(specFile,'utf8'));const base=arg('--base',path.join(directory,'.cache/base.dat'));
  if(!fs.existsSync(base))throw Error('Initialize the reusable world once: node TOOLS/scenarios/assemble.cjs --init [--base existing.sav]');
  if(!arg('--base')&&JSON.parse(fs.readFileSync(base+'.json','utf8')).exeSha256!==snapshot.sha(game()['KB2.EXE']))throw Error('Base world belongs to another game build; initialize it again');
  const layout=sourceLayout(path.join(ROOT,'WEB/.build/dev/build/SRC/DIST/KB2.EXE'));semantic.compile(layout,semantic.decode(layout,fs.readFileSync(base)),spec);
  const temporary=path.join(directory,'.assemble-'+process.pid+'.tmp');
  process.env.KB2_ASSEMBLE_STARTED=String(started);
  try{
    child('--capture',{output:temporary,base,spec:specFile});child('--verify',{output:temporary});
    const bytes=fs.readFileSync(temporary),receipt=JSON.parse(fs.readFileSync(temporary+'.receipt','utf8'));
    const metadata={format:2,type:'dosbox-x-snapshot',title:spec.title,...snapshot.compatibility(ROOT,game()),snapshotSha256:snapshot.sha(bytes),snapshotBytes:bytes.length,frameSha256:receipt.frameSha256,frameMask:receipt.frameMask};
    fs.writeFileSync(temporary+'.json',JSON.stringify(metadata,null,2)+'\n');
    fs.renameSync(temporary,path.join(directory,spec.id+'.sav'));fs.renameSync(temporary+'.json',path.join(directory,spec.id+'.json'));
    const recipes=path.join(directory,'recipes');fs.mkdirSync(recipes,{recursive:true});fs.writeFileSync(path.join(recipes,spec.id+'.json'),JSON.stringify(spec,null,2)+'\n');
    console.log('READY',JSON.stringify({id:spec.id,seconds:(Date.now()-started)/1000,path:path.join(directory,spec.id+'.sav')}));
  }finally{for(const suffix of ['','.receipt','.json','.rgb'])if(fs.existsSync(temporary+suffix))fs.unlinkSync(temporary+suffix);}
}
if(require.main===module){process.on('uncaughtException',error=>{console.error(error.stack);process.exit(1);});main().then(()=>process.exit(0)).catch(error=>{console.error(error.stack);process.exit(1);});}
module.exports={game,cleanBase,capture,verify,main};
