const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),{spawnSync}=require('node:child_process');
const {sourceLayout,ROOT}=require('../TOOLS/scenarios/headless.cjs'),S=require('../TOOLS/scenarios/semantic.cjs');
const layout=sourceLayout(path.join(ROOT,'WEB/.build/dev/build/SRC/DIST/KB2.EXE'));
const blank=new S.State(layout,Buffer.alloc(layout.campaign.size));
blank.put('Island',1);blank.put('Hero',{x:20,y:20});blank.put('Difficulty',6);blank.put('Days',200);blank.put('UnlockedIslands',1);
blank.put('Army',{$all:{species:100,count:0}});blank.put('Mutants',{$all:{defense:10,cost:{price:10}}});
blank.put('Castles',{$all:{$all:{species:{$all:100}}}});blank.put('WanderingArmies',{$all:{$all:{species:{$all:100}}}});
const spec={version:1,id:'test',title:'Проверка'},base=blank.bytes;
const compile=patch=>S.compile(layout,base,{...spec,...patch});
const {protectBootSleep}=require('../TOOLS/scenarios/headless.cjs'),mock={},calls=[];let ready=false;const finish=protectBootSleep(mock,()=>ready);mock.sync_sleep=wake=>{calls.push('async');wake();};mock.sync_sleep(()=>calls.push('boot'));assert.deepEqual(calls,['boot']);ready=true;mock.sync_sleep(()=>calls.push('game'));finish();mock.sync_sleep(()=>calls.push('normal'));assert.deepEqual(calls,['boot','async','game','async','normal']);
const frame=require('../TOOLS/scenarios/frame.cjs'),rgb=Buffer.alloc(640*350*3,7),animated=Buffer.from(rgb);animated[(150*640+510)*3]=1;assert.deepEqual(frame.normalize(rgb,['magic']),frame.normalize(animated,['magic']));animated[0]=1;assert.notDeepEqual(frame.normalize(rgb,['magic']),frame.normalize(animated,['magic']));assert.throws(()=>frame.normalize(rgb,['anything']),/mask/);
const art=require('../TOOLS/scenarios/art.cjs'),tile=Buffer.from(Array.from({length:2880},(_,i)=>i%256)),original=Buffer.from(tile);art.mirror(tile);assert.notDeepEqual(tile,original);art.mirror(tile);assert.deepEqual(tile,original);
assert.deepEqual(S.coverage(layout).uncovered,[]);assert.equal(S.coverage(layout).fields,69);
assert.deepEqual(S.decode(layout,S.encode(layout,base)),base,'Campaign packing round trip');
const full=compile({
  hero:{hero:{x:30,y:31},difficulty:'hard',leadership:100000,damageBonus:20},
  economy:{gold:500000,income:400,cargo:{'ЖЕМЧУГ':8},carpenters:9,woodcutters:4,stonecutters:3,diggers:2},
  army:{active:[{species:'ЭЛЬФЫ',count:20}],reserve:[{species:'ДРАКОНЫ',count:2}],siegeEngineOwned:true,mutants:{25:{name:'ТЕСТ',weeks:7,appearance:5,shots:8,retaliations:2,flies:true,defense:80,attack:20}}},
  magic:{magicPower:20,scrolls:{'МОРОЗ':3},scrollCapacity:50,spellAvailable:{$all:true},hiddenSpellIsland:3,hiddenSpellPosition:{x:10,y:20},guardianSpecies:{$all:100}},
  progress:{unlockedIslands:5,localMapOwned:{1:true},relics:{2:{owned:true}},contracts:{1:{1:{island:2,slot:3}}}},
  ancientMaps:{1:true,3:true},calendar:{weeks:8,days:1,extraDays:200},
  world:{map:{1:{12:{12:'water'}}},towns:{1:{1:{x:15,y:15,workers:{1:4}}}}},
  ship:{shipOwned:true,ship:{x:12,y:12},shipIsland:1,shipBackground:48},
  runtime:{goodsStock:{$all:20},goodsBuyPrices:{$all:100},workerRestockPhase:false},roamers:{timeStopAccumulated:200}
});
for(const [field,value]of Object.entries({'Hero.X':30,'Hero.Y':31,Difficulty:4,Gold:500000,'Cargo.7':8,'Army.0.Species':5,'Army.5.Species':23,'Flags.ArmyAvailable':1,'Flags.SiegeEngineOwned':1,'Mutants.25.Cost.Price':1287,'Mutants.25.Flags':200,'Scrolls.10':3,'Flags.SpellAvailable.7':1,MapParts:2,'Map.1.15.15':7,'Map.1.12.12':48,'Flags.ShipOwned':1}))assert.equal(full.state.get(field),value,field);
assert.equal(full.live['Runtime.GoodsStock'].length,7);assert.equal(full.live['Runtime.WorkerRestockPhase'][0],0);
assert.deepEqual(S.decode(layout,S.encode(layout,full.state.bytes)),full.state.bytes);
const removed=compile({world:{wanderingArmies:{1:{0:{x:255}}}}});assert.equal(removed.state.get('WanderingArmies.1.0.X'),255);
const relocated=compile({world:{castles:{1:{1:{x:10,y:11}}}}});assert.equal(relocated.state.get('Map.1.9.11'),1);assert.equal(relocated.state.get('Map.1.10.11'),2);assert.equal(relocated.state.get('Map.1.11.11'),3);
const random=require('../TOOLS/scenarios/random.cjs');assert.equal(random.wizard(36).seed,670952883);for(const [name,id]of Object.entries(random.offers))assert.equal(random.wizard(random.forOffer(name)).offer,id);
for(const [patch,pattern]of [
  [{economy:{goold:2}},/Unknown/],[{economy:{gold:-1}},/gold/],
  [{army:{active:[{species:'НЕИЗВЕСТНЫЕ',count:1}]}},/creature/],
  [{army:{active:[{species:1,count:0}]}},/count/],
  [{progress:{localMapOwned:{0:true}}},/1..5/],
  [{progress:{localMapOwned:{1:1}}},/boolean/],
  [{ancientMaps:{1:true},progress:{mapParts:0}},/contradicts/],
  [{location:{position:{x:20,y:20},near:{kind:'wizard'}}},/Choose/],
  [{view:{kind:'dialog',target:'wizard',offer:'ancientMap'}},/relations/],
  [{view:{kind:'near',target:'toString'}},/Unknown/],
  [{runtime:{picturePage:0}},/Unknown/],[{world:{map:{1:{66:{0:0}}}}},/0..65/],
  [{army:{mutants:{25:{appearance:30}}}},/0..24/],
  [{world:{towns:{1:{1:{x:20,y:20}},2:{x:20,y:20}}}},/Unknown|object|index/]
])assert.throws(()=>compile(patch),pattern);
const battle=compile({army:{active:[{species:'ЭЛЬФЫ',count:40}]},view:{kind:'battle',target:'army',slot:0},battle:{enemies:[{species:'СКЕЛЕТЫ',count:15},{species:'ЗОМБИ',count:10}],player:{0:{shots:1,hitPoints:300,initialCount:40}},poison:{0:2}}});
assert.equal(battle.state.get('WanderingArmies.1.0.Species.0'),3);assert.equal(battle.state.get('WanderingArmies.1.0.Counts.1'),10);
console.log('PASS semantic fields, packing, all domains, names, derived state and rejection checks');
if(process.argv.includes('--native')){
  const ix=process.argv.indexOf('--base'),nativeBase=process.argv[ix+1];if(ix<0||!nativeBase)throw Error('Native checks need --base <cached campaign>');
  const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'kb2-semantic-'));
  const cases=[
    {id:'world',title:'Составное состояние',hero:{leadership:100000},economy:{gold:123456,cargo:{'ЖЕМЧУГ':5},carpenters:4},army:{active:[{species:'ЭЛЬФЫ',count:40}],reserve:[{species:'ДРАКОНЫ',count:1}],siegeEngineOwned:true},magic:{magicPower:12,scrolls:{'МОРОЗ':2},spellAvailable:{$all:true}},progress:{localMapOwned:{1:true},relics:{2:{owned:true}}},calendar:{weeks:12,days:1,extraDays:8},ship:{shipOwned:true},view:{kind:'world'}},
    {id:'town',title:'Рынок города',economy:{gold:9000},runtime:{goodsStock:{$all:1},goodsBuyPrices:{$all:100},goodsSellPrices:{$all:90}},view:{kind:'dialog',target:'town',slot:1,section:'goods'}},
    {id:'castle',title:'Карта замка куплена',economy:{gold:9000},progress:{localMapOwned:{1:true}},view:{kind:'dialog',target:'castle',slot:1}},
    {id:'battle',title:'Бой с ограниченным боезапасом',hero:{leadership:100000},army:{active:[{species:'ЭЛЬФЫ',count:40}],reserve:[]},view:{kind:'battle',target:'army',slot:0},battle:{enemies:[{species:'СКЕЛЕТЫ',count:15},{species:'ЗОМБИ',count:10}],player:{0:{shots:1,hitPoints:300,initialCount:40}},poison:{0:2}}},
    {id:'single',title:'Бой с одним отрядом',hero:{leadership:100000},army:{active:[{species:'ЭЛЬФЫ',count:40}],reserve:[]},view:{kind:'battle',target:'army',slot:0},battle:{enemies:[{species:'СКЕЛЕТЫ',count:15}],player:{0:{shots:0,position:{x:1,y:0}}},enemy:{0:{position:{x:4,y:4}}},terrain:{'3,2':'forest'}}},
    {id:'siege',title:'Осада',hero:{leadership:100000},army:{active:[{species:'ЭЛЬФЫ',count:40}],reserve:[]},view:{kind:'battle',target:'castle',slot:2},battle:{enemies:[{species:'СКЕЛЕТЫ',count:15},{species:'ЗОМБИ',count:10}]}},
    {id:'guardian',title:'Стражи заклинания',hero:{leadership:100000},army:{active:[{species:'ЭЛЬФЫ',count:40}],reserve:[]},world:{map:{1:{6:{19:'guardian'}}}},view:{kind:'battle',target:'guardian'},battle:{enemies:[{species:'СКЕЛЕТЫ',count:15},{species:'ЗОМБИ',count:10}]}},
    {id:'mage',title:'Чёрный маг',view:{kind:'dialog',target:'mage'}},
    {id:'offer',title:'Предложение волшебника',progress:{wizardRelations:{1:5}},view:{kind:'dialog',target:'wizard',offer:'transmute'}},
    {id:'ritual',title:'Мастерская ритуального камня',hero:{difficulty:'impossible'},army:{active:[{species:'ЭЛЬФЫ',count:20},{species:'ДРАКОНЫ',count:1}]},magic:{magicPower:12,ritualPower:40,spellAvailable:{$all:true},ritualStoneIsland:1,ritualStonePosition:{x:6,y:19}},world:{map:{1:{6:{19:'stone'}}}},view:{kind:'dialog',target:'ritualStone'}},
  ];
  try{
    const selected=process.argv.includes('--case')?process.argv[process.argv.indexOf('--case')+1].split(','):cases.map(c=>c.id);
    for(const item of cases.filter(c=>selected.includes(c.id))){const file=path.join(temporary,item.id+'.recipe.json');fs.writeFileSync(file,JSON.stringify({version:1,...item}));const result=spawnSync(process.execPath,[path.join(ROOT,'TOOLS/scenarios/assemble.cjs'),'--directory',temporary,'--base',nativeBase,'--spec',file],{encoding:'utf8',windowsHide:true,timeout:90000});process.stdout.write(result.stdout);assert.equal(result.status,0,result.stderr);}
    console.log('PASS native multi-domain world, town market, castle and configured combat');
  }finally{assert.ok(path.resolve(temporary).startsWith(path.resolve(os.tmpdir())+path.sep));fs.rmSync(temporary,{recursive:true,force:true});}
}
