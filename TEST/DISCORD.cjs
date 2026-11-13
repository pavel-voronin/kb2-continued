const assert = require('node:assert/strict');
const {messages, send} = require('../RELEASE/discord.cjs');

(async () => {
  const release = {tag: 'v1.0.2', changes: '- Карта земли текущего острова оплачивается только при её отсутствии.\n- Часть древней карты оплачивается только при её отсутствии.',
    releaseUrl: 'https://github.com/pavel-voronin/kb2-continued/releases/tag/v1.0.2'};
  const [payload] = messages(release);
  assert.equal(payload.content, '**KB2: Продолжение — 1.0.2**\n\n' + release.changes + '\n\n' +
    '[Скачать](https://github.com/pavel-voronin/kb2-continued/releases/download/v1.0.2/KB2-continued-v1.0.2-win64-portable.zip), распаковать и запустить `START.BAT`.\n\n' +
    '[Играть в браузере](https://kb2.pavelvoronin.com/)');
  assert.deepEqual(payload.allowed_mentions, {parse: []});
  assert.equal(payload.flags, 4); // SUPPRESS_EMBEDS: keep links without previews.
  const long = {...release, changes: '- @everyone <@123> ' + '🧙'.repeat(3000) + '\n- Последний пункт.'};
  const parts = messages(long);
  assert.ok(parts.length > 1);
  for (const part of parts) {
    assert.ok(part.content.length <= 2000);
    assert.ok(!/[\uD800-\uDBFF]$/.test(part.content));
    assert.deepEqual(part.allowed_mentions, {parse: []});
    assert.equal(part.flags, 4);
  }
  assert.ok(parts.map(p => p.content).join('').includes(long.changes));
  assert.throws(() => messages({...release, changes: ''}), /empty/);
  let calls = 0;
  const webhook = 'https://discord.com/api/webhooks/123/test-secret';
  const ids = await send(webhook, [payload], async (url, options) => {
    calls++;
    assert.equal(url, webhook + '?wait=true');
    assert.equal(options.method, 'POST');
    assert.deepEqual(JSON.parse(options.body), payload);
    return {ok: true, json: async () => ({id: '456'})};
  });
  assert.equal(calls, 1);
  assert.deepEqual(ids, ['456']);
  await assert.rejects(send('', [payload]), /DISCORD_WEBHOOK_URL/);
  await assert.rejects(send(webhook, [payload], async () => ({ok: false, status: 429})), /HTTP 429/);
  await assert.rejects(send(webhook, [payload], async () => { throw new Error(webhook); }), error =>
    !error.message.includes('test-secret') && error.message.includes('check the channel'));
  await assert.rejects(send(webhook, [payload], async () => ({ok: true, json: async () => ({})})), /confirm/);
  console.log('PASS: approved text, long changes, mentions disabled, confirmed send and failures.');
})().catch(error => { console.error(error); process.exitCode = 1; });
