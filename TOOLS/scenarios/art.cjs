// Loaded 96x60 EGA tile cache, four 720-byte bitplanes. Preparation only.
// Equivalent to KBGfx.MirrorTileArt; the game executable is never patched.
const reversed=Uint8Array.from({length:256},(_,value)=>{let n=0;for(let i=0;i<8;i++)n=(n<<1)|((value>>>i)&1);return n;});
function mirror(bytes){if(bytes.length!==2880)throw Error('Expected a 96x60 four-plane tile');for(let plane=0;plane<4;plane++)for(let row=0;row<60;row++){const start=plane*720+row*12,copy=Buffer.from(bytes.subarray(start,start+12));for(let i=0;i<12;i++)bytes[start+i]=reversed[copy[11-i]];}}
function mirrorTile(run,tile){const pointer=run.field('Runtime.PictureBanks').readUInt32LE((tile>>>4)*4),at=run.ram+(pointer>>>16)*16+(pointer&65535)+(tile&15)*2880;mirror(Buffer.from(run.mod.HEAPU8.buffer,at,2880));}
module.exports={mirror,mirrorTile};
