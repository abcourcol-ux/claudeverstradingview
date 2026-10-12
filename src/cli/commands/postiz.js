import { register } from '../router.js';
import * as core from '../../core/postiz.js';

const list = (v) => (v ? v.split(',').map((s) => s.trim()).filter(Boolean) : undefined);

const postOptions = {
  content: { type: 'string', short: 'c', description: 'Post text' },
  channels: { type: 'string', description: 'Comma-separated channel ids/identifiers/names (default: all active)' },
  type: { type: 'string', short: 't', description: 'now (default), schedule, draft' },
  date: { type: 'string', short: 'd', description: 'ISO date for --type schedule' },
};

register('postiz', {
  description: 'Publish chart analysis to social networks via Postiz (needs POSTIZ_API_KEY)',
  subcommands: new Map([
    ['channels', {
      description: 'List connected Postiz channels',
      handler: () => core.listIntegrations(),
    }],
    ['post', {
      description: 'Create a post, optionally with images',
      options: {
        ...postOptions,
        images: { type: 'string', short: 'i', description: 'Comma-separated local image paths' },
      },
      handler: (o) => core.createPost({
        content: o.content, integration_ids: list(o.channels), image_paths: list(o.images) || [], type: o.type, date: o.date,
      }),
    }],
    ['share', {
      description: 'Screenshot the chart and post it',
      options: {
        ...postOptions,
        region: { type: 'string', short: 'r', description: 'chart (default), full, strategy_tester' },
      },
      handler: (o) => core.shareChart({
        content: o.content, integration_ids: list(o.channels), region: o.region, type: o.type, date: o.date,
      }),
    }],
  ]),
});
