// Only these two HUD pictures animate while the world waits for input.
// Hash all other pixels; emulator memory/VGA still restore without alteration.
const rectangles={magic:[496,142,96,60],wealth:[496,202,96,60]};
function validate(masks){if(masks===undefined)return;if(!Array.isArray(masks)||masks.length>2||new Set(masks).size!==masks.length||masks.some(name=>!Object.hasOwn(rectangles,name)))throw Error('Invalid animated HUD mask');}
function normalize(bytes,masks=[]){validate(masks);if(!masks.length)return bytes;if(bytes.length!==640*350*3)throw Error('Unexpected EGA frame size');const copy=Buffer.from(bytes);for(const name of masks){const [x,y,w,h]=rectangles[name];for(let row=y;row<y+h;row++)copy.fill(0,(row*640+x)*3,(row*640+x+w)*3);}return copy;}
module.exports={rectangles,normalize,validate};
