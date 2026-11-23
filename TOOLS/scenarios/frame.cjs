// Only these two HUD pictures animate while the world waits for input.
// Hash all other pixels; emulator memory/VGA still restore without alteration.
const rectangles={magic:[496,142,96,60],wealth:[496,202,96,60]};
function validate(masks){if(masks===undefined)return;if(!Array.isArray(masks)||masks.length>2||new Set(masks).size!==masks.length||masks.some(name=>!Object.hasOwn(rectangles,name)))throw Error('Invalid animated HUD mask');}
function normalize(bytes,masks=[]){validate(masks);if(!masks.length)return bytes;if(bytes.length!==640*350*3)throw Error('Unexpected EGA frame size');const copy=Buffer.from(bytes);for(const name of masks){const [x,y,w,h]=rectangles[name];for(let row=y;row<y+h;row++)copy.fill(0,(row*640+x)*3,(row*640+x+w)*3);}return copy;}

// Match a completed black phase of KBBDraw.PulseCell. Waiting for this phase
// lets the verifier compare the entire battle frame without masking pixels.
function blackBattleCursor(bytes,{x,y}) {
  const left=x*96+18,top=y*60+23;
  const black=(dx,dy)=>{
    const i=((top+dy)*640+left+dx)*3;
    return bytes[i]===0&&bytes[i+1]===0&&bytes[i+2]===0;
  };
  for(const row of [0,1,49,50]){
    for(let offset=0;offset<16;offset++){
      if(!black(offset,row)||!black(60+offset,row))return false;
    }
  }
  for(const column of [-1,0,1,74,75,76]){
    for(let offset=0;offset<=10;offset++){
      if(!black(column,offset)||!black(column,40+offset))return false;
    }
  }
  return true;
}
module.exports={rectangles,normalize,validate,blackBattleCursor};
