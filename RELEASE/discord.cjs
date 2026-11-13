const fs = require('node:fs');

function messages({tag, changes, releaseUrl}) {
  if (!/^[vV][0-9]+(?:\.[0-9]+){0,2}(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$/.test(tag)) {
    throw new Error('Invalid release tag.');
  }
  if (!changes?.trim()) throw new Error('Release changes are empty.');
  if (!/^https:\/\/github\.com\/[^/]+\/[^/]+\/releases\/tag\//.test(releaseUrl)) {
    throw new Error('Invalid release URL.');
  }
  const downloadUrl = releaseUrl.replace('/releases/tag/', '/releases/download/') +
    `/KB2-continued-${tag}-win64-portable.zip`;
  let remaining = `**KB2: Продолжение — ${tag.slice(1)}**\n\n${changes}\n\n` +
    `[Скачать](${downloadUrl}), распаковать и запустить \`START.BAT\`.\n\n` +
    '[Играть в браузере](https://kb2.pavelvoronin.com/)';
  const result = [];
  while (remaining.length) {
    let end = Math.min(2000, remaining.length);
    if (end < remaining.length) {
      const newline = remaining.lastIndexOf('\n', end - 1);
      if (newline >= 0) end = newline + 1;
      // Keep surrogate pairs together if a single line exceeds Discord's limit.
      if (/[\uD800-\uDBFF]/.test(remaining[end - 1])) end--;
    }
    result.push({content: remaining.slice(0, end), allowed_mentions: {parse: []}, flags: 4});
    remaining = remaining.slice(end);
  }
  return result;
}

async function send(webhook, payloads, request = fetch) {
  if (!/^https:\/\/discord\.com\/api\/webhooks\/\d+\/[A-Za-z0-9_-]+$/.test(webhook || '')) {
    throw new Error('Set repository secret DISCORD_WEBHOOK_URL to a Discord webhook URL.');
  }
  const ids = [];
  for (const payload of payloads) {
    let response;
    try {
      response = await request(`${webhook}?wait=true`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload), signal: AbortSignal.timeout(30000), redirect: 'error'
      });
    } catch {
      // Network errors may contain the secret URL. Do not log or retry them.
      throw new Error('Discord request failed; check the channel before retrying.');
    }
    if (!response.ok) throw new Error(`Discord returned HTTP ${response.status}.`);
    const message = await response.json();
    if (!message.id) throw new Error('Discord did not confirm message creation.');
    ids.push(message.id);
  }
  return ids;
}

module.exports = {messages, send};

if (require.main === module) {
  (async () => {
    const release = JSON.parse(fs.readFileSync(process.argv[2], 'utf8').replace(/^\uFEFF/, ''));
    if (release.isDraft) throw new Error('Cannot announce a draft release.');
    const payloads = messages({tag: release.tagName, changes: process.env.RELEASE_CHANGES, releaseUrl: release.url});
    const ids = await send(process.env.DISCORD_WEBHOOK_URL, payloads);
    console.log(`Discord messages confirmed: ${ids.join(', ')}`);
  })().catch(error => { console.error(error.message); process.exitCode = 1; });
}
