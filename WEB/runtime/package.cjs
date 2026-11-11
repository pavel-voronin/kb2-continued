// Preserve the matching js-dos browser worker/sockdrive footer from emulators 8.5.3.
const fs = require('node:fs');
const path = require('node:path');
const web = path.resolve(__dirname, '..');
const stock = fs.readFileSync(path.join(web, 'runtime/vendor/wdosbox-x.js'), 'utf8');
const marker = 'define([],()=>WDOSBOXX);';
const end = stock.indexOf(marker);
if (end < 0) throw new Error('Не найден конец модуля emulators 8.5.3');
const footer = stock.slice(stock.indexOf('\n', end) + 1);
if (!footer.includes('wc-install')) throw new Error('Не найдена обвязка Worker');
const source = process.argv[2];
const out = path.join(web, 'runtime/vendor');
fs.mkdirSync(out, {recursive:true});
fs.writeFileSync(path.join(out, 'wdosbox-x.js'), fs.readFileSync(path.join(source, 'wdosbox-x.js'), 'utf8') + '\n' + footer);
fs.copyFileSync(path.join(source, 'wdosbox-x.wasm'), path.join(out, 'wdosbox-x.wasm'));
const manifestPath=path.join(out,'manifest.json');
const manifest=JSON.parse(fs.readFileSync(manifestPath));
for(const name of Object.keys(manifest.files))manifest.files[name]=require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(out,name))).digest('hex');
fs.writeFileSync(manifestPath,JSON.stringify(manifest,null,2)+'\n');
