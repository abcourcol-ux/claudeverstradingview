import { z } from 'zod';
import { jsonResult } from './_format.js';
import * as core from '../core/postiz.js';

const postFields = {
  content: z.string().describe('Post text (e.g. your chart analysis / bias summary)'),
  integration_ids: z.array(z.string()).optional().describe('Postiz channels to post to — channel id, provider identifier ("x", "telegram", "linkedin"...) or channel name. Defaults to ALL active channels. Use postiz_list_channels to see them.'),
  type: z.enum(['now', 'schedule', 'draft']).optional().describe('now (default) publishes immediately, schedule needs date, draft saves without publishing'),
  date: z.string().optional().describe('ISO date/time for type=schedule (e.g. "2026-10-13T08:00:00Z")'),
  settings: z.record(z.string(), z.record(z.string(), z.any())).optional().describe('Per-provider settings overrides keyed by identifier, e.g. { "reddit": { "subreddit": [...] } }. Sensible defaults are applied for X.'),
};

export function registerPostizTools(server) {
  server.tool('postiz_list_channels', 'List the social channels connected in Postiz (X, LinkedIn, Telegram, Discord...). Requires POSTIZ_API_KEY.', {}, async () => {
    try { return jsonResult(await core.listIntegrations()); }
    catch (err) { return jsonResult({ success: false, error: err.message }, true); }
  });

  server.tool('postiz_create_post', 'Publish, schedule or draft a social post through Postiz, optionally with local images (e.g. screenshots from capture_screenshot).', {
    ...postFields,
    image_paths: z.array(z.string()).optional().describe('Local image files to attach (png/jpg/gif/webp)'),
  }, async (args) => {
    try { return jsonResult(await core.createPost(args)); }
    catch (err) { return jsonResult({ success: false, error: err.message }, true); }
  });

  server.tool('postiz_share_chart', 'Screenshot the live TradingView chart and post it with your analysis through Postiz in one step. Always show the user the text and target channels and get confirmation before calling with type=now.', {
    ...postFields,
    region: z.string().optional().describe('Screenshot region: chart (default), full, strategy_tester'),
  }, async (args) => {
    try { return jsonResult(await core.shareChart(args)); }
    catch (err) { return jsonResult({ success: false, error: err.message }, true); }
  });
}
