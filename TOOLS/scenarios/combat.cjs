// Native Battle has a local stack frame, not a global Game field. Resolve it
// once offline from initialized army signatures; never scan a running browser.
const {State}=require('./semantic.cjs');
const {wait}=require('./headless.cjs');
const allowed=['player','enemy','terrain','cursor','roundMagicReady','enemyPhaseFinished','demonHalved','mutantResists','dragonResists','demonResists','frozenEnemySlot','retaliations','poison','leadershipLimit','vampireInitialCount','maxReserve','uncontrolled','canMove'];
const units=['count','hitPoints','attackPower','initialCount','shots','canFly','position'];
function bind(run){
  const schema=run.layout.battle,player=schema.fields.Player,unit=player.item,signature=Buffer.alloc(5);
  signature[0]=run.field('Campaign.Army')[0];
  const heap=Buffer.from(run.mod.HEAPU8.buffer),start=run.ram,end=start+0xa0000,found=[];
  let at=start-1;
  while((at=heap.indexOf(signature.subarray(0,1),at+1))>=0&&at<end){
    const base=at-player.offset;if(base<start||base+schema.size>end)continue;
    const state=new State({...run.layout,campaign:schema},heap.subarray(base,base+schema.size));
    if(state.get('PlayerCount')!==run.field('Runtime.BattleField').filter(n=>n>=112&&n<=124).length||state.get('EnemyCount')<1||state.get('EnemyCount')>5||state.get('CursorX')>5||state.get('CursorY')>4)continue;
    let valid=true;for(let i=0;i<10;i++){const army=run.field('Campaign.Army'),species=army[i*3],count=army.readUInt16LE(i*3+1);if(state.get('Player.'+i+'.Species')!==species||(species<30&&(state.get('Player.'+i+'.Count')>count||state.get('Player.'+i+'.Count')===0||state.get('Player.'+i+'.HitPoints')<1))){valid=false;break;}}
    if(valid)found.push({base,state});
  }
  if(found.length!==1)throw Error('Cannot uniquely bind native combat stack ('+found.length+')');return found[0];
}
async function configure(run,spec,press){
  const {base,state}=bind(run),grid=run.field('Runtime.BattleField'),counts=run.field('Runtime.BattleDistances');
  const positions={};for(let x=0;x<6;x++)for(let y=0;y<5;y++){const cell=grid[x*5+y];if(cell>=112&&cell<=124)positions['Player.'+((cell-112)/3)]=[x,y];else if(cell>=32&&cell<=44)positions['Enemy.'+((cell-32)/3)]=[x,y];}
  for(const side of ['player','enemy'])if(spec[side]){
    if(!spec[side]||typeof spec[side]!=='object'||Array.isArray(spec[side]))throw Error('battle.'+side+' must be indexed slots');
    for(const [slot,patch]of Object.entries(spec[side])){
      if(!/^\d+$/.test(slot)||Number(slot)>9||(side==='enemy'&&Number(slot)>4))throw Error('Invalid battle slot');
      if(!patch||typeof patch!=='object'||Array.isArray(patch))throw Error('Invalid battle unit');
      for(const key of Object.keys(patch))if(!units.includes(key))throw Error('Unknown battle unit field '+key);
      const prefix=(side==='player'?'Player':'Enemy')+'.'+slot;
      if(state.get(prefix+'.Species')>=30)throw Error('Battle patch targets an empty slot');
      if(patch.position){const {x,y}=patch.position;if(Object.keys(patch.position).some(k=>!['x','y'].includes(k))||!Number.isInteger(x)||x<0||x>5||!Number.isInteger(y)||y<0||y>4)throw Error('Battle position outside 6x5 field');if(!positions[prefix])throw Error('Reserve has no field position');positions[prefix]=[x,y];}
      for(const [key,value]of Object.entries(patch))if(key!=='position')state.put(prefix+'.'+key[0].toUpperCase()+key.slice(1),value);
      const species=state.get(prefix+'.Species'),campaign=new State(run.layout,run.field('Campaign'));
      const defense=species<25?run.layout.creatures[species].defense:campaign.get('Mutants.'+species+'.Defense'),attack=species<25?run.layout.creatures[species].attack:campaign.get('Mutants.'+species+'.Attack');
      if(patch.hitPoints!==undefined&&patch.count===undefined)state.put(prefix+'.Count',Math.ceil(patch.hitPoints/defense));
      if(patch.count!==undefined&&patch.hitPoints===undefined)state.put(prefix+'.HitPoints',patch.count*defense);
      const count=state.get(prefix+'.Count');
      if(patch.count!==undefined||patch.hitPoints!==undefined){
        if(patch.attackPower===undefined)state.put(prefix+'.AttackPower',count*attack);
        if(patch.initialCount===undefined)state.put(prefix+'.InitialCount',Math.max(count,side==='player'?campaign.get('Army.'+slot+'.Count'):state.get(prefix+'.InitialCount')));
      }
      if(count<1||state.get(prefix+'.InitialCount')<count||state.get(prefix+'.HitPoints')<1||Math.ceil(state.get(prefix+'.HitPoints')/defense)!==count||state.get(prefix+'.AttackPower')<0)throw Error('Inconsistent battle count/health/initialCount');
    }
  }
  for(const key of allowed.filter(k=>!['player','enemy','cursor','terrain'].includes(k)))if(spec[key]!==undefined)state.put(key[0].toUpperCase()+key.slice(1),spec[key]);
  for(let i=0;i<grid.length;i++)if(grid[i]>=112&&grid[i]<=124||grid[i]>=32&&grid[i]<=44){grid[i]=0;counts.writeUInt16LE(0,i*2);}
  if(spec.terrain){for(const [position,terrain]of Object.entries(spec.terrain)){const match=/^([0-5]),([0-4])$/.exec(position),tile={clear:0,swamp:48,forest:64,mountain:80}[terrain];if(!match||tile===undefined)throw Error('Invalid battle terrain '+position);grid[+match[1]*5+(+match[2])]=tile;}}
  const occupied=new Set();for(const [prefix,[x,y]]of Object.entries(positions)){const at=x*5+y;if(occupied.has(at)||grid[at]!==0)throw Error('Battle unit/terrain collision');occupied.add(at);const [side,slot]=prefix.split('.');grid[at]=(side==='Player'?112:32)+Number(slot)*3;counts.writeUInt16LE(state.get(prefix+'.Count'),at*2);}
  state.put('ReadyPlayerCount',Array.from({length:5},(_,i)=>positions['Player.'+i]&&!state.get('CanMove.'+i)?1:0).reduce((a,b)=>a+b));
  const desired=spec.cursor||{x:state.get('CursorX'),y:state.get('CursorY')};
  if(!Number.isInteger(desired.x)||desired.x<0||desired.x>5||!Number.isInteger(desired.y)||desired.y<0||desired.y>4)throw Error('Invalid battle cursor');
  // Keep the native loop at a real AwaitCellKey boundary. Repaint each changed
  // cell using its ordinary cursor handler, so all cached artwork stays valid.
  // Delay round-boundary effects until after the offline repaint.
  const magic=state.get('RoundMagicReady'),ready=state.get('ReadyPlayerCount');state.put('RoundMagicReady',false);state.put('ReadyPlayerCount',0);
  Buffer.from(run.mod.HEAPU8.buffer,base,state.bytes.length).set(state.bytes);
  let x=state.get('CursorX'),y=state.get('CursorY');
  async function go(tx,ty){while(x!==tx){const dx=x<tx?1:-1;await press(run,dx>0?77:75);x+=dx;}while(y!==ty){const dy=y<ty?1:-1;await press(run,dy>0?80:72);y+=dy;}}
  await go(0,0);for(let row=0;row<5;row++){await go(row%2?0:5,row);if(row<4)await go(row%2?0:5,row+1);}await go(desired.x,desired.y);
  const live=Buffer.from(run.mod.HEAPU8.buffer,base,state.bytes.length);live[state.node('RoundMagicReady').offset]=magic;live[state.node('ReadyPlayerCount').offset]=ready;
  await wait(()=>run.keyboardEmpty(),'combat repaint complete');return {base,size:state.bytes.length};
}
module.exports={bind,configure,allowed,units};
