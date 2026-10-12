/**
 * Postiz integration — publish chart analysis to social networks.
 * Uses the Postiz public API (https://github.com/gitroomhq/postiz-app):
 *   GET  /public/v1/integrations  → connected channels
 *   POST /public/v1/upload        → upload media (multipart, field "file")
 *   POST /public/v1/posts         → create / schedule a post
 *
 * Config (env):
 *   POSTIZ_API_KEY  — API key from Postiz Settings → Public API (required)
 *   POSTIZ_URL      — backend URL, default https://api.postiz.com
 *                     (self-hosted: your backend URL, e.g. https://postiz.example.com/api)
 */
import { openAsBlob, existsSync } from 'node:fs';
import { basename, extname } from 'node:path';
import { captureScreenshot } from './capture.js';

const DEFAULT_URL = 'https://api.postiz.com';

const MIME = {
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
};

// Provider settings that Postiz validates as required when publishing.
// Anything not listed defaults to { __type: identifier }.
const DEFAULT_SETTINGS = {
  x: { who_can_reply_post: 'everyone' },
};

function getConfig() {
  const apiKey = process.env.POSTIZ_API_KEY;
  if (!apiKey) {
    throw new Error(
      'POSTIZ_API_KEY is not set. Create an API key in Postiz (Settings → Public API) and export it, ' +
        'or add it to the "env" block of the MCP server config.',
    );
  }
  const baseUrl = (process.env.POSTIZ_URL || DEFAULT_URL).replace(/\/+$/, '');
  return { apiKey, baseUrl };
}

async function request(path, { method = 'GET', body, json } = {}) {
  const { apiKey, baseUrl } = getConfig();
  const headers = { Authorization: apiKey };
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(json);
  }

  const res = await fetch(`${baseUrl}/public/v1${path}`, { method, headers, body });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }

  if (!res.ok) {
    const msg = (data && (data.msg || data.message)) || text || res.statusText;
    throw new Error(`Postiz ${method} ${path} failed (${res.status}): ${typeof msg === 'string' ? msg : JSON.stringify(msg)}`);
  }
  return data;
}

export async function listIntegrations() {
  const integrations = await request('/integrations');
  return {
    success: true,
    count: integrations.length,
    integrations: integrations.map((i) => ({
      id: i.id,
      name: i.name,
      identifier: i.identifier,
      disabled: i.disabled,
      profile: i.profile,
    })),
  };
}

export async function uploadMedia({ file_path } = {}) {
  if (!file_path) throw new Error('file_path is required');
  if (!existsSync(file_path)) throw new Error(`File not found: ${file_path}`);

  const type = MIME[extname(file_path).toLowerCase()];
  if (!type) throw new Error(`Unsupported image type: ${file_path} (use png, jpg, gif or webp)`);

  const form = new FormData();
  form.append('file', await openAsBlob(file_path, { type }), basename(file_path));
  const media = await request('/upload', { method: 'POST', body: form });
  return { success: true, id: media.id, path: media.path };
}

/**
 * Build the Postiz CreatePostDto payload. Exported for unit tests.
 */
export function buildPostPayload({ content, integrations, media = [], type = 'now', date, settings = {} }) {
  if (!content || !content.trim()) throw new Error('content is required');
  if (!integrations?.length) throw new Error('At least one integration is required');
  if (!['now', 'schedule', 'draft'].includes(type)) {
    throw new Error(`Invalid type "${type}" — use now, schedule or draft`);
  }
  if (type === 'schedule' && !date) throw new Error('date is required when type is "schedule"');

  let isoDate = new Date().toISOString();
  if (date) {
    const d = new Date(date);
    if (Number.isNaN(d.getTime())) throw new Error(`Invalid date: ${date}`);
    isoDate = d.toISOString();
  }

  return {
    type,
    date: isoDate,
    shortLink: false,
    tags: [],
    posts: integrations.map(({ id, identifier }) => ({
      integration: { id },
      value: [{ content, image: media.map(({ id: mid, path }) => ({ id: mid, path })) }],
      settings: {
        __type: identifier,
        ...(DEFAULT_SETTINGS[identifier] || {}),
        ...(settings[identifier] || {}),
      },
    })),
  };
}

async function resolveIntegrations(integration_ids) {
  const { integrations } = await listIntegrations();
  const active = integrations.filter((i) => !i.disabled);

  if (!integration_ids?.length) {
    if (!active.length) throw new Error('No active Postiz channels connected');
    return active;
  }

  return integration_ids.map((ref) => {
    const match = active.find(
      (i) => i.id === ref || i.identifier === ref || i.name?.toLowerCase() === String(ref).toLowerCase(),
    );
    if (!match) {
      throw new Error(
        `No active Postiz channel matches "${ref}". Available: ` +
          active.map((i) => `${i.name} (${i.identifier}, ${i.id})`).join(', '),
      );
    }
    return match;
  });
}

export async function createPost({ content, integration_ids, image_paths = [], type, date, settings } = {}) {
  const integrations = await resolveIntegrations(integration_ids);
  const media = [];
  for (const file_path of image_paths) media.push(await uploadMedia({ file_path }));

  const payload = buildPostPayload({ content, integrations, media, type, date, settings });
  const result = await request('/posts', { method: 'POST', json: payload });

  return {
    success: true,
    type: payload.type,
    date: payload.date,
    channels: integrations.map((i) => `${i.name} (${i.identifier})`),
    media_count: media.length,
    result,
  };
}

/**
 * Screenshot the live chart and post it with the given text.
 */
export async function shareChart({ content, integration_ids, region = 'chart', type, date, settings } = {}) {
  const shot = await captureScreenshot({ region });
  if (!shot.file_path) throw new Error('Screenshot did not produce a file');
  const res = await createPost({ content, integration_ids, image_paths: [shot.file_path], type, date, settings });
  return { ...res, screenshot: shot.file_path };
}
