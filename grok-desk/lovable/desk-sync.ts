// Fonction Edge Supabase "desk-sync" : seule porte d'entrée du desk (PC) vers la base.
// Secret requis : DESK_SYNC_SECRET (le même que dans grok-desk/.env). Désactiver la vérification JWT (verify_jwt = false).
import { createClient } from "npm:@supabase/supabase-js@2";

const BOTS = new Set(["scanner", "news", "planner", "risk", "skeptic", "chef"]);
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  const secret = Deno.env.get("DESK_SYNC_SECRET");
  if (req.method !== "POST" || !secret || req.headers.get("x-desk-secret") !== secret) {
    return json({ error: "unauthorized" }, 401);
  }
  const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { action, data } = await req.json().catch(() => ({}));
  let error = null;

  switch (action) {
    case "message":
      if (!BOTS.has(data?.bot)) return json({ error: "bad bot" }, 400);
      ({ error } = await sb.from("desk_messages").insert({ bot: data.bot, text: String(data.text).slice(0, 4000) }));
      break;
    case "round":
      ({ error } = await sb.from("desk_rounds").insert(data));
      break;
    case "positions":
      if (Array.isArray(data) && data.length) {
        ({ error } = await sb.from("desk_positions").upsert(data.map((p) => ({ ...p, updated_at: new Date().toISOString() }))));
      }
      break;
    case "status":
      ({ error } = await sb.from("desk_status").upsert({ id: 1, data, updated_at: new Date().toISOString() }));
      break;
    case "commands": {
      const { data: rows, error: e } = await sb.from("desk_commands").select("id, command, arg")
        .eq("status", "pending").order("created_at").limit(10);
      if (e) return json({ error: e.message }, 500);
      if (rows?.length) await sb.from("desk_commands").update({ status: "taken" }).in("id", rows.map((r) => r.id));
      return json({ commands: rows ?? [] });
    }
    case "command_done":
      ({ error } = await sb.from("desk_commands").update({ status: "done", result: data?.result ?? "ok", done_at: new Date().toISOString() }).eq("id", data?.id));
      break;
    default:
      return json({ error: "unknown action" }, 400);
  }
  return error ? json({ error: error.message }, 500) : json({ ok: true });
});
