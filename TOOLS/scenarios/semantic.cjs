// Offline declarative game state. No addresses, key sequences or VM internals
// belong in scenario descriptions. Array keys use the game's original indexes.
const assert=require('node:assert/strict');
const random=require('./random.cjs');
const groups={
  hero:['Hero','Island','Difficulty','Leadership','LeadershipBonus','DamageBonus'],
  economy:['Gold','Income','Cargo','CargoMaxPrices','Carpenters','Woodcutters','Stonecutters','Diggers'],
  army:['Army','Mutants','WeeklySpecies','EnemyGrace'],
  magic:['Scrolls','ScrollCapacity','MagicPower','RitualPower','SpellColors','HiddenSpellIsland','HiddenSpellPosition','HiddenSpellEffect','RitualStoneIsland','RitualStonePosition','GuardianSpecies','GuardianCounts','TornadoCharges'],
  progress:['VisitedCastles','VisitedTowns','Contracts','QuestFlags','WizardRelations','WizardVisited','Relics','ContractIsland','ContractSlot','HighestVisitedIsland','UnlockedIslands','SceneIsland','MapParts','ArchivedIsland','ArchiveMarker'],
  calendar:['Weeks','Days','ExtraDays'],
  world:['Map','Castles','Towns','Dwellings','WanderingArmies','Underground'],
  ship:['Ship','ShipIsland','ShipHeading','ShipBackground'],
};
const flags={
  hero:['ArmyAvailable','Heading','InstructionsShown'],
  army:['SiegeEngineOwned'],magic:['SpellAvailable','SpellUsed'],
  progress:['Discovery','LocalMapOwned','PaperChartPresent'],ship:['ShipOwned'],
};
const runtime=['WorkerRestockPhase','RegrowthPosition','RegrowthCountdown','ShoreTile','SpiritStonePosition','InstructionCounter','ShipAbandonBlocked','GoodsMarketAge','GoodsMarketTown','GoodsMarketIsland','GoodsStock','GoodsBuyPrices','GoodsSellPrices','CurrentContractOffer'];
const worldRuntime=['WizardPosition','WizardAge','MagePosition','MageAge','TimeStopAccumulated'];
const tiles={grass:0,castle:2,road:4,army:5,town:7,dwelling:8,chart:9,treasure:10,underground:11,wizard:12,ship:14,ownedCastle:18,stone:22,guardian:23,mage:28,sand:32,water:48,mountain:64};
const targets={wizard:12,mage:28,town:7,castle:2,dwelling:8,army:5,chart:9,treasure:10,underground:11,stone:22,ritualStone:22,guardian:23,ship:14};
const reports={workers:17,rituals:19,contract:23,help:24,army:30,dismiss:32,status:47,cargo:48,map:50,magic:22};
const sections={wizard:{workers:[2,49],travel:[4,51],instructions:[5,52],contract:[5,52]},town:{contract:[2,49],workers:[7,54],goods:[8,55]},castle:{audience:[3,50],garrison:[]}};
const lower=name=>name[0].toLowerCase()+name.slice(1);
const object=(v,label)=>{if(!v||typeof v!=='object'||Array.isArray(v))throw Error(label+' must be an object');};
function keys(value,allowed,label){object(value,label);for(const key of Object.keys(value))if(!allowed.includes(key))throw Error('Unknown '+label+'.'+key);}
function integer(v,min,max,label){if(!Number.isSafeInteger(v)||v<min||v>max)throw Error(label+' must be '+min+'..'+max);return v;}

class State {
  constructor(layout,bytes){this.layout=layout;this.bytes=Buffer.from(bytes);assert.equal(this.bytes.length,layout.campaign.size);this.touched=new Set();}
  node(path){let node=this.layout.campaign,offset=0;for(const key of path.split('.')){if(node.fields){node=node.fields[key];if(!node)throw Error('Unknown state field '+path);offset+=node.offset;}else{const index=integer(Number(key),node.lo,node.hi,path);offset+=(index-node.lo)*node.item.size;node=node.item;}}return {node,offset};}
  get(path){const {node,offset}=this.node(path);if(node.fields||node.item||node.string)throw Error('Not a scalar '+path);return this.bytes['read'+(node.signed?'Int':'UInt')+(node.size*8)+'LE']?.(offset)??(node.signed?this.bytes.readInt8(offset):this.bytes[offset]);}
  put(path,value){const {node,offset}=this.node(path);this.patch(node,offset,value,path);this.touched.add(path);}
  patch(node,at,value,label){
    if(node.fields){
      object(value,label);value={...value};
      if(node.kind==='TCreatureDefinition'){
        let bits=this.bytes[at+node.fields.Flags.offset],price=this.bytes.readUInt16LE(at+node.fields.Cost.offset);
        for(const [key,max,shift,mask]of [['shots',31,0,31],['retaliations',3,5,96],['flies',1,7,128]])if(value[key]!==undefined){let v=value[key];if(key==='flies'){if(typeof v!=='boolean')throw Error(label+'.flies must be boolean');v=+v;}integer(v,0,max,label+'.'+key);bits=(bits&~mask)|(v<<shift);delete value[key];value.flags=bits;}
        for(const [key,shift,mask]of [['weeks',0,255],['appearance',8,65280]])if(value[key]!==undefined){const v=integer(value[key],0,key==='appearance'?24:255,label+'.'+key);price=(price&~mask)|(v<<shift);delete value[key];value.cost={price};}
      }
      const names=Object.keys(node.fields);for(const [name,item]of Object.entries(value)){const original=names.find(n=>lower(n)===name||n===name);if(!original)throw Error('Unknown '+label+'.'+name);const field=node.fields[original];this.patch(field,at+field.offset,item,label+'.'+original);}return;
    }
    if(node.item){
      if(Array.isArray(value)){if(value.length!==node.hi-node.lo+1)throw Error(label+' requires '+(node.hi-node.lo+1)+' entries (or sparse indexed object)');value=Object.fromEntries(value.map((v,i)=>[i+node.lo,v]));}
      object(value,label);for(let [index,item]of Object.entries(value)){if(index==='$all'){for(let i=node.lo;i<=node.hi;i++)this.patch(node.item,at+(i-node.lo)*node.item.size,item,label+'.'+i);}else{
        const catalogs=this.layout.catalogs||{},catalog=/Scrolls$/.test(label)?catalogs.ScrollNames:/Cargo(?:MaxPrices)?$/.test(label)?catalogs.GoodsNames:null;
        if(catalog&&!/^-?\d+$/.test(index)){const found=catalog.find(n=>n.name.toLocaleLowerCase('ru')===index.toLocaleLowerCase('ru'));if(found)index=String(found.id);}
        if(!/^-?\d+$/.test(index))throw Error('Invalid index '+label+'.'+index);const i=integer(Number(index),node.lo,node.hi,label);this.patch(node.item,at+(i-node.lo)*node.item.size,item,label+'.'+i);}}return;
    }
    if(node.string){if(typeof value!=='string'||value.length>node.string)throw Error(label+' exceeds '+node.string+' characters');const decoder=new TextDecoder('ibm866'),alphabet=decoder.decode(Uint8Array.from({length:256},(_,i)=>i));const chars=[...value].map(c=>{const n=alphabet.indexOf(c);if(n<0)throw Error('Not CP866: '+c);return n;});this.bytes.fill(0,at,at+node.size);this.bytes[at]=chars.length;this.bytes.set(chars,at+1);return;}
    if(/Species(?:\.\d+)?$/.test(label)&&typeof value==='string'){const found=this.layout.creatures.find(c=>c.name.toLocaleLowerCase('ru')===value.toLocaleLowerCase('ru'));if(!found)throw Error('Unknown creature '+value);value=found.id;}
    if(/^Map\.\d+\.\d+\.\d+$/.test(label)&&typeof value==='string'){if(!Object.hasOwn(tiles,value))throw Error('Unknown terrain '+value);value=tiles[value];}
    if(label==='Difficulty'&&typeof value==='string')value={easy:6,normal:5,hard:4,impossible:3}[value];
    if(node.boolean){if(typeof value!=='boolean')throw Error(label+' must be boolean');value=Number(value);}
    const bits=node.size*8;integer(value,node.signed?-(2**(bits-1)):0,node.signed?2**(bits-1)-1:2**bits-1,label);
    if(node.size===1)this.bytes[node.signed?'writeInt8':'writeUInt8'](value,at);else this.bytes['write'+(node.signed?'Int':'UInt')+bits+'LE'](value,at);
  }
}
function decode(layout,packed){
  const count=layout.campaign.fields.Flags.size,head=Math.ceil(count/8);
  if(packed.length!==head+layout.campaign.size-count)throw Error('Invalid campaign size');
  const bytes=Buffer.alloc(layout.campaign.size);for(let i=0;i<count;i++)bytes[i]=(packed[i>>3]>>(i&7))&1;
  Buffer.from(packed).copy(bytes,count,head);return bytes;
}
function encode(layout,bytes){const count=layout.campaign.fields.Flags.size,head=Math.ceil(count/8),packed=Buffer.alloc(head+bytes.length-count);for(let i=0;i<count;i++)if(bytes[i])packed[i>>3]|=1<<(i&7);bytes.copy(packed,head,count);return packed;}
function coverage(layout){
  const covered=Object.values(groups).flat(),uncovered=Object.keys(layout.campaign.fields).filter(n=>n!=='Flags'&&!covered.includes(n));
  const flagCoverage=Object.values(flags).flat();uncovered.push(...Object.keys(layout.campaign.fields.Flags.fields).filter(n=>!flagCoverage.includes(n)).map(n=>'Flags.'+n));
  return {domains:Object.keys(groups),fields:covered.length+flagCoverage.length,uncovered};
}
function enemyPaths(kind,island,slot){if(kind==='guardian')return ['GuardianSpecies','GuardianCounts'];const record=(kind==='castle'?'Castles':'WanderingArmies')+'.'+island+'.'+(slot??(kind==='castle'?1:0));return [record+'.Species',record+'.Counts'];}
function compile(layout,base,spec){
  keys(spec,['version','id','title','seed',...Object.keys(groups),'runtime','roamers','ancientMaps','location','view','battle'],'scenario');
  if(spec.version!==1)throw Error('Semantic scenario version must be 1');
  if(!/^[a-z0-9][a-z0-9-]{0,79}$/.test(spec.id||'')||typeof spec.title!=='string'||!spec.title.trim()||spec.title.length>120)throw Error('Invalid scenario id/title');
  const state=new State(layout,base);
  for(const [domain,names]of Object.entries(groups))if(spec[domain]){
    const allowed=[...names,...flags[domain]||[]].map(lower);if(domain==='army')allowed.push('active','reserve');keys(spec[domain],allowed,domain);
    for(const [key,value]of Object.entries(spec[domain])){
      if(key==='active'||key==='reserve'){
        if(!Array.isArray(value)||value.length>5)throw Error('army.'+key+' requires up to five stacks');
        for(let i=0;i<5;i++){const stack=value[i],p='Army.'+(i+(key==='reserve'?5:0));if(stack){keys(stack,['species','count'],'army stack');state.put(p,stack);}else state.put(p,{species:100,count:0});}
      }else{const field=names.find(n=>lower(n)===key);state.put(field||'Flags.'+flags[domain].find(n=>lower(n)===key),value);}
    }
  }
  if(spec.army&&(spec.army.active||spec.army.reserve||spec.army.army)){
    const available=Array.from({length:10},(_,i)=>state.get('Army.'+i+'.Species')).some(n=>n<30);
    if(spec.hero?.armyAvailable!==undefined&&spec.hero.armyAvailable!==available)throw Error('armyAvailable contradicts army composition');state.put('Flags.ArmyAvailable',available);
  }
  if(spec.ancientMaps){object(spec.ancientMaps,'ancientMaps');for(const [island,owned]of Object.entries(spec.ancientMaps)){integer(+island,1,5,'ancient map island');if(typeof owned!=='boolean')throw Error('ancientMaps ownership must be boolean');const p='WizardVisited.'+island,v=state.get(p);state.put(p,owned?v|2:v&253);}}
  const parts=Array.from({length:5},(_,i)=>state.get('WizardVisited.'+(i+1))&2?1:0).reduce((a,b)=>a+b);
  if(spec.progress?.mapParts!==undefined&&spec.progress.mapParts!==parts)throw Error('mapParts contradicts ancient map ownership');state.put('MapParts',parts);
  const live={};for(const [name,allowed,schema]of [['runtime',runtime,layout.runtime],['roamers',worldRuntime,layout.world]])if(spec[name]){
    keys(spec[name],allowed.map(lower),name);for(const [key,value]of Object.entries(spec[name])){const field=allowed.find(n=>lower(n)===key),node=schema.fields[field],buffer=Buffer.alloc(node.size);const proxy=Object.create(State.prototype);proxy.bytes=buffer;proxy.layout=layout;proxy.patch(node,0,value,name+'.'+field);live[(name==='runtime'?'Runtime.':'World.')+field]=buffer;}
  }
  if(spec.location){keys(spec.location,['island','position','near'],'location');if(spec.location.island!==undefined)state.put('Island',integer(spec.location.island,1,5,'island'));if(spec.location.position){keys(spec.location.position,['x','y'],'position');state.put('Hero',spec.location.position);}if(spec.location.position&&spec.location.near)throw Error('Choose position or near');}
  const island=state.get('Island');integer(island,1,5,'island');integer(state.get('Difficulty'),3,6,'difficulty');integer(state.get('Days'),1,255,'days');
  integer(state.get('Hero.X'),2,63,'hero.x');integer(state.get('Hero.Y'),2,63,'hero.y');
  integer(state.get('Gold'),0,2147483647,'gold');integer(state.get('UnlockedIslands'),1,5,'unlocked islands');
  for(let i=0;i<10;i++){const creature=state.get('Army.'+i+'.Species'),count=state.get('Army.'+i+'.Count');if(creature!==100){integer(creature,0,29,'army creature');integer(count,1,65535,'army count');}}
  for(let i=0;i<8;i++)integer(state.get('SpellColors.'+i),0,7,'ritual color');
  for(let i=25;i<=29;i++){integer(state.get('Mutants.'+i+'.Defense'),1,65535,'mutant defense');integer(state.get('Mutants.'+i+'.Cost.Price')>>>8,0,24,'mutant appearance');}
  for(let land=1;land<=5;land++){
    integer(state.get('WizardRelations.'+land),0,10,'wizard relations');
    for(let slot=0;slot<8;slot++){integer(state.get('Dwellings.'+land+'.'+slot+'.Species'),0,29,'dwelling species');}
    for(const [kind,lo,hi]of [['Castles',1,5],['WanderingArmies',0,20]])for(let slot=lo;slot<=hi;slot++)for(let i=0;i<5;i++){
      const p=kind+'.'+land+'.'+slot,creature=state.get(p+'.Species.'+i);if(creature!==100){integer(creature,0,29,p+' creature');integer(state.get(p+'.Counts.'+i),1,65535,p+' count');}
    }
  }
  // Moving a structured world object also moves its map marker. Sparse patches
  // cannot leave an invisible dwelling or a castle pointing to the old tile.
  const before=new State(layout,base);
  for(const [field,tile,lo,hi]of [['Castles',2,1,5],['Towns',7,1,5],['Dwellings',8,0,7],['WanderingArmies',5,0,20],['Underground',11,1,2]]){
    for(let land=1;land<=5;land++)for(let slot=lo;slot<=hi;slot++){
      const p=field+'.'+land+'.'+slot,x=state.get(p+'.X'),y=state.get(p+'.Y'),ox=before.get(p+'.X'),oy=before.get(p+'.Y');
      const owned=field==='Castles'&&state.get(p+'.Owned'),oldOwned=field==='Castles'&&before.get(p+'.Owned');
      if(x===ox&&y===oy&&owned===oldOwned)continue;
      const from='Map.'+land+'.'+ox+'.'+oy,to='Map.'+land+'.'+x+'.'+y;
      if(field==='WanderingArmies'&&x===255){if(ox>=0&&ox<=65&&oy>=0&&oy<=65&&state.get(from)===5)state.put(from,0);continue;}
      integer(x,2,63,p+'.x');integer(y,2,63,p+'.y');
      if(ox>=0&&ox<=65&&oy>=0&&oy<=65&&[tile,field==='Castles'?18:tile].includes(state.get(from)))state.put(from,0);
      if(field==='Castles'&&(x!==ox||y!==oy))for(const [dx,value]of [[-1,1],[1,3]])if(ox+dx>=0&&ox+dx<=65&&oy>=0&&oy<=65){const at='Map.'+land+'.'+(ox+dx)+'.'+oy;if(state.get(at)===value)state.put(at,0);}
      if(state.get(to)!==0&&!(x===ox&&y===oy))throw Error('World object collision at '+land+':'+x+','+y);
      state.put(to,owned?18:tile);
      if(field==='Castles'&&(x!==ox||y!==oy))for(const [dx,value]of [[-1,1],[1,3]]){const at='Map.'+land+'.'+(x+dx)+'.'+y;if(state.get(at)!==0)throw Error('Castle footprint collision');state.put(at,value);}
    }
  }
  const view=spec.view||{kind:'world'};keys(view,['kind','target','slot','offer','report','section'],'view');
  if(!['world','near','dialog','report','battle'].includes(view.kind))throw Error('Unknown view '+view.kind);
  const near=spec.location?.near||(view.target?{kind:view.target,slot:view.slot}:null);
  if(near){keys(near,['kind','slot'],'near');if(!Object.hasOwn(targets,near.kind))throw Error('Unknown encounter '+near.kind);if(near.slot!==undefined)integer(near.slot,near.kind==='dwelling'||near.kind==='army'?0:1,near.kind==='army'?20:near.kind==='dwelling'?7:near.kind==='underground'?2:5,'near.slot');}
  if(near?.kind==='ritualStone'&&state.get('RitualStoneIsland')!==island)throw Error('Ritual stone is on island '+state.get('RitualStoneIsland')+'; specify that island');
  if(['near','dialog','battle'].includes(view.kind)&&!near)throw Error('Encounter view needs a target');
  if(view.kind==='dialog'&&['ship','underground'].includes(near.kind))throw Error('This encounter has no waiting dialog; use a near view');
  if(view.target&&near&&view.target!==near.kind)throw Error('View target contradicts location.near');
  if(view.kind==='report'&&!Object.hasOwn(reports,view.report))throw Error('Unknown report '+view.report);
  if(view.section){if(view.kind!=='dialog'||!Object.hasOwn(sections[near?.kind]||{},view.section))throw Error('Unknown encounter section');if(near.kind==='wizard'){
    if(view.section==='travel'&&state.get('WizardRelations.'+island)<2)throw Error('Travel requires wizard relations >=2');
    if(['contract','instructions'].includes(view.section)&&(state.get('WizardRelations.'+island)<3||(view.section==='instructions')!==(state.get('MagicPower')>=10)))throw Error('Wizard hint section contradicts relations/magic power');
  }if(near.kind==='castle'){const p='Castles.'+island+'.'+(near.slot??1),owned=state.get(p+'.Owned');if((view.section==='garrison')!==!!owned)throw Error('Castle section contradicts ownership');if(view.section==='audience'&&((near.slot??1)!==1||state.get('QuestFlags.'+island)>=10))throw Error('Audience needs a peaceful lord castle');}}
  if(view.offer!==undefined&&(near?.kind!=='wizard'||!Object.hasOwn(random.offers,view.offer)||view.kind!=='dialog'))throw Error('Unsupported offer');
  if(view.offer!==undefined&&state.get('WizardRelations.'+island)<5)throw Error('Wizard special offer requires relations >=5');
  if(view.kind==='battle'&&!['army','castle','guardian'].includes(near.kind))throw Error('Battle needs an army, hostile castle or guardian');
  if(view.kind==='battle'&&near.kind==='castle'){
    if(state.get('Castles.'+island+'.'+(near.slot??1)+'.Owned'))throw Error('Cannot besiege an owned castle');
    if(spec.army?.siegeEngineOwned===false)throw Error('Siege requires a siege engine');state.put('Flags.SiegeEngineOwned',true);
    if((near.slot??1)===1){if(spec.progress?.questFlags?.[island]!==undefined&&state.get('QuestFlags.'+island)<10)throw Error('Lord castle must be hostile for a siege');state.put('QuestFlags.'+island,100);}
  }
  if(spec.battle){keys(spec.battle,['enemies',...require('./combat.cjs').allowed],'battle');if(view.kind!=='battle')throw Error('battle configuration requires battle view');if(spec.battle.enemies){const n=spec.battle.enemies.length;if(!Array.isArray(spec.battle.enemies)||n<1||n>5)throw Error('battle.enemies needs 1..5 stacks');const [species,counts]=enemyPaths(near.kind,island,near.slot);for(let i=0;i<5;i++){const stack=spec.battle.enemies[i];if(stack){keys(stack,['species','count'],'enemy');state.put(species+'.'+i,stack.species);state.put(counts+'.'+i,integer(stack.count,1,65535,'enemy count'));integer(state.get(species+'.'+i),0,29,'enemy species');}else{state.put(species+'.'+i,100);state.put(counts+'.'+i,0);}}}}
  if(view.kind==='battle'&&!Array.from({length:5},(_,i)=>state.get('Army.'+i+'.Species')).some(n=>n<30))throw Error('Battle requires an active army');
  const seed=integer(spec.seed??(view.offer?random.forOffer(view.offer):36),0,0xffffffff,'seed');
  if(view.offer&&random.wizard(seed).offer!==random.offers[view.offer])throw Error('seed contradicts the requested wizard offer');
  return {state,live,view,near,seed,spec};
}
module.exports={State,compile,encode,decode,coverage,groups,flags,tiles,targets,reports,sections,runtime,worldRuntime,enemyPaths};
