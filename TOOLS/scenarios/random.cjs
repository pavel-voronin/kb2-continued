// Turbo Pascal's RandSeed/Random; native calls still execute in the emulator.
const offers={scrolls:1,ancientMap:2,workers:3,troops:4,transmute:5,damage:6};
function next(seed){return Number((BigInt(seed)*134775813n+1n)&0xffffffffn);}
function random(seed,limit){const value=next(seed);return {seed:value,value:Number(BigInt(value)*BigInt(limit)>>32n)};}
function wizard(seed){const first=random(seed,79),second=random(first.seed,79);let result=random(second.seed,10);while(result.value+1>=7)result=random(result.seed,10);return {offer:result.value+1,seed:result.seed,direction:Math.floor(first.value/10),mageDirection:Math.floor(second.value/10)};}
function forOffer(name){if(!Object.hasOwn(offers,name))throw Error('Unknown wizard offer '+name);for(let seed=0;seed<100000;seed++){const result=wizard(seed);if(result.offer===offers[name]&&result.direction===1)return seed;}throw Error('Cannot seed wizard offer');}
module.exports={next,random,wizard,forOffer,offers};
