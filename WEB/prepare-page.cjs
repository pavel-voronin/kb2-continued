// Refresh the static page without rebuilding either DOS game.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { unzipSync } = require('fflate');

function readRelease(markdown,tag) {
  const sections=[];let fence=null;
  for(const line of markdown.replace(/\r/g,'').split('\n')) {
    const marker=line.match(/^ {0,3}(`{3,}|~{3,})/);
    if(marker){if(!fence)fence=marker[1];else if(marker[1][0]===fence[0] && line.trim().length>=fence.length && /^(`+|~+)$/.test(line.trim()))fence=null;continue;}
    if(fence)continue;
    const match=line.match(/^ {0,3}##\s+(\d+(?:\.\d+){0,2}(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?)\s+—\s+(\d{4}-\d{2}-\d{2})\s*$/);
    if(match)sections.push({version:match[1],date:match[2]});
  }
  const version=tag?tag.replace(/^[vV]/,''):sections[0]?.version;
  const matches=sections.filter(s=>s.version===version);
  if(matches.length!==1)throw new Error('CHANGELOG.md: expected exactly one section for '+(tag||'latest release'));
  return matches[0];
}

function renderHtml(html,data,startup,revision,runtime) {
  return html
    .replaceAll('{{VERSION}}', JSON.parse(data).version)
    .replaceAll('{{ASSET_REV}}', revision)
    .replaceAll('{{RUNTIME_REV}}', runtime)
    .replace('{{STARTUP_IMAGE}}', 'data:image/png;base64,' + startup.toString('base64'))
    .replace('<!-- release-data -->', `<script type="application/json" id="release-data">${data}</script>`);
}

function preparePage({tag}={}) {
  const root = path.resolve(__dirname, '..');
  const out = path.join(__dirname, 'dist');
  const markdown = fs.readFileSync(path.join(root, 'CHANGELOG.md'), 'utf8');
  const {version,date}=readRelease(markdown,tag);
  const bundles = {};
  let bundle;
  for (const mode of ['classic', 'continued']) {
    const bytes = fs.readFileSync(path.join(out, 'games', mode + '.jsdos'));
    bundles[mode] = crypto.createHash('sha256').update(bytes).digest('hex').slice(0, 16);
    if (mode === 'continued') bundle = unzipSync(bytes);
  }
  const font = bundle['KB2.FNT'];
  if (!font || font.length !== 240 * 8) throw new Error('Не найден игровой шрифт KB2.FNT');
  const runtimeHash = crypto.createHash('sha256');
  for (const name of ['wdosbox-x.js', 'wdosbox-x.wasm']) runtimeHash.update(fs.readFileSync(path.join(out, 'vendor', name)));
  const runtime = runtimeHash.digest('hex').slice(0, 16);
  const data = JSON.stringify({ version, date, markdown, bundles, runtime, font: Buffer.from(font).toString('base64') }).replace(/</g, '\\u003c');
  const startup = fs.readFileSync(path.join(__dirname, 'assets/startup.png'));
  const hash = crypto.createHash('sha256').update(data);
  hash.update(startup);
  for (const name of ['style.css', 'changelog.js', 'save-files.js', 'app.js', 'favicon.ico',
    'favicon-16.png', 'favicon-32.png', 'favicon-48.png', 'favicon-64.png']) {
    const bytes = fs.readFileSync(path.join(__dirname, name));
    hash.update(bytes);
    fs.writeFileSync(path.join(out, name), bytes);
  }
  const revision = hash.digest('hex').slice(0, 12);
  const html = renderHtml(fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8'), data, startup, revision, runtime);
  fs.writeFileSync(path.join(out, 'index.html'), html);
  return version;
}

module.exports = preparePage;
module.exports.readRelease = readRelease;
module.exports.renderHtml = renderHtml;
if (require.main === module) {
  try { console.log('Локальная страница: ' + preparePage()); }
  catch (error) { console.error(error); process.exitCode = 1; }
}
