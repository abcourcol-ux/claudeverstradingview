/**
 * Postiz integration unit tests — uses a local mock Postiz API, no TradingView needed.
 *
 * Run: node --test tests/postiz.test.js
 */
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { writeFileSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import * as postiz from '../src/core/postiz.js';

const INTEGRATIONS = [
  { id: 'int-x', name: 'My X', identifier: 'x', disabled: false, profile: 'me' },
  { id: 'int-tg', name: 'Trading TG', identifier: 'telegram', disabled: false, profile: 'chan' },
  { id: 'int-li', name: 'Old LinkedIn', identifier: 'linkedin', disabled: true, profile: 'me' },
];

let server;
const calls = [];

before(async () => {
  server = createServer((req, res) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      const body = Buffer.concat(chunks);
      calls.push({ method: req.method, url: req.url, headers: req.headers, body });
      res.setHeader('Content-Type', 'application/json');
      if (req.headers.authorization !== 'test-key') {
        res.statusCode = 401;
        return res.end(JSON.stringify({ msg: 'Invalid API key' }));
      }
      if (req.url === '/public/v1/integrations') return res.end(JSON.stringify(INTEGRATIONS));
      if (req.url === '/public/v1/upload') return res.end(JSON.stringify({ id: 'media-1', path: 'https://cdn.example/m1.png' }));
      if (req.url === '/public/v1/posts') return res.end(JSON.stringify([{ postId: 'p1', integration: 'int-x' }]));
      res.statusCode = 404;
      res.end(JSON.stringify({ msg: 'not found' }));
    });
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  process.env.POSTIZ_URL = `http://127.0.0.1:${server.address().port}/`;
  process.env.POSTIZ_API_KEY = 'test-key';
});

after(() => server.close());

describe('postiz — buildPostPayload', () => {
  it('builds a CreatePostDto with provider settings and defaults', () => {
    const p = postiz.buildPostPayload({
      content: 'BTC bias long',
      integrations: [{ id: 'a', identifier: 'x' }, { id: 'b', identifier: 'telegram' }],
      media: [{ id: 'm', path: 'https://cdn/m.png' }],
    });
    assert.equal(p.type, 'now');
    assert.equal(p.shortLink, false);
    assert.deepEqual(p.tags, []);
    assert.deepEqual(p.posts[0].settings, { __type: 'x', who_can_reply_post: 'everyone' });
    assert.deepEqual(p.posts[1].settings, { __type: 'telegram' });
    assert.deepEqual(p.posts[1].value, [{ content: 'BTC bias long', image: [{ id: 'm', path: 'https://cdn/m.png' }] }]);
  });

  it('merges user settings overrides', () => {
    const p = postiz.buildPostPayload({
      content: 'hi', integrations: [{ id: 'a', identifier: 'x' }],
      settings: { x: { who_can_reply_post: 'following' } },
    });
    assert.equal(p.posts[0].settings.who_can_reply_post, 'following');
  });

  it('validates inputs', () => {
    const integrations = [{ id: 'a', identifier: 'x' }];
    assert.throws(() => postiz.buildPostPayload({ content: ' ', integrations }), /content/);
    assert.throws(() => postiz.buildPostPayload({ content: 'x', integrations: [] }), /integration/);
    assert.throws(() => postiz.buildPostPayload({ content: 'x', integrations, type: 'later' }), /Invalid type/);
    assert.throws(() => postiz.buildPostPayload({ content: 'x', integrations, type: 'schedule' }), /date is required/);
    assert.throws(() => postiz.buildPostPayload({ content: 'x', integrations, date: 'nope' }), /Invalid date/);
    const s = postiz.buildPostPayload({ content: 'x', integrations, type: 'schedule', date: '2026-10-13T08:00:00Z' });
    assert.equal(s.date, '2026-10-13T08:00:00.000Z');
  });
});

describe('postiz — API calls (mock server)', () => {
  it('lists integrations with the API key header', async () => {
    const r = await postiz.listIntegrations();
    assert.equal(r.count, 3);
    assert.equal(calls.at(-1).headers.authorization, 'test-key');
  });

  it('resolves channels by identifier/name, uploads image and posts', async () => {
    const img = join(tmpdir(), `postiz-test-${process.pid}.png`);
    writeFileSync(img, Buffer.from([0x89, 0x50, 0x4e, 0x47]));
    try {
      calls.length = 0;
      const r = await postiz.createPost({ content: 'ES1! long above 5800', integration_ids: ['x', 'trading tg'], image_paths: [img] });
      assert.equal(r.success, true);
      assert.deepEqual(r.channels, ['My X (x)', 'Trading TG (telegram)']);

      const upload = calls.find((c) => c.url === '/public/v1/upload');
      assert.match(upload.headers['content-type'], /multipart\/form-data/);
      assert.match(upload.body.toString('latin1'), /name="file"; filename="postiz-test-/);

      const post = JSON.parse(calls.find((c) => c.url === '/public/v1/posts').body);
      assert.deepEqual(post.posts.map((p) => p.integration.id), ['int-x', 'int-tg']);
      assert.deepEqual(post.posts[0].value[0].image, [{ id: 'media-1', path: 'https://cdn.example/m1.png' }]);
    } finally {
      unlinkSync(img);
    }
  });

  it('defaults to all active channels and skips disabled ones', async () => {
    calls.length = 0;
    await postiz.createPost({ content: 'hello', type: 'draft' });
    const post = JSON.parse(calls.find((c) => c.url === '/public/v1/posts').body);
    assert.deepEqual(post.posts.map((p) => p.integration.id), ['int-x', 'int-tg']);
  });

  it('rejects unknown or disabled channels', async () => {
    await assert.rejects(postiz.createPost({ content: 'x', integration_ids: ['linkedin'] }), /No active Postiz channel matches "linkedin"/);
  });

  it('surfaces API errors and missing key', async () => {
    process.env.POSTIZ_API_KEY = 'bad';
    await assert.rejects(postiz.listIntegrations(), /401.*Invalid API key/);
    delete process.env.POSTIZ_API_KEY;
    await assert.rejects(postiz.listIntegrations(), /POSTIZ_API_KEY is not set/);
    process.env.POSTIZ_API_KEY = 'test-key';
  });
});
