// ginot-hair-mcp - hosted read-only MCP (Streamable HTTP, stateless JSON replies).
// Free Cloudflare Worker: no secrets, no bindings, no write tools. Reads only the
// public data.json on GitHub Pages. Objection dates are DERIVED, not official.
import { filterPlans } from "./api.mjs";

const ORIGIN = "https://reihlinstinct.github.io/ginot-hair-plans/data.json";
const PROTOCOL = "2024-11-05";
const NOTE = "Derived from publication dates (60 days); not a verified official deadline. Check the plan's source page.";
const FIELDS = ["pl_number", "pl_name", "station_desc", "internet_short_status", "entity_subtype_desc",
  "receiving_date", "open_date", "depositing_date", "pl_last_deposit_date",
  "objection_deadline_derived_60d_from_publication", "pl_area_dunam", "mavat_url",
  "last_update_date", "land_status", "land_status_date"];
const pub = (r) => Object.fromEntries(FIELDS.filter((k) => k in r).map((k) => [k, r[k]]));
const clamp = (v, lo, hi, d) => Math.min(Math.max(Number.isFinite(+v) ? Math.trunc(+v) : d, lo), hi);

export const TOOLS = [
  { name: "search_plans", description: "Search public plans by text in number/name/status/type.",
    inputSchema: { type: "object", properties: { query: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 50 } } } },
  { name: "get_plan", description: "Get one public plan by pl_number.",
    inputSchema: { type: "object", properties: { pl_number: { type: "string" } }, required: ["pl_number"] } },
  { name: "upcoming_objection_windows", description: "Deposit-stage plans whose DERIVED objection window ends within N days. " + NOTE,
    inputSchema: { type: "object", properties: { days: { type: "integer", minimum: 0, maximum: 365 }, as_of: { type: "string", description: "YYYY-MM-DD" } } } },
  { name: "data_status", description: "Dataset generation date and plan count.", inputSchema: { type: "object", properties: {} } },
];

export function callTool(data, name, args = {}) {
  const rows = data.rows || [];
  if (name === "search_plans") {
    const q = String(args.query || "").trim().toLowerCase();
    const limit = clamp(args.limit, 1, 50, 20);
    const hits = rows.filter((r) => !q || ["pl_number", "pl_name", "station_desc", "entity_subtype_desc"]
      .map((k) => r[k] || "").join(" ").toLowerCase().includes(q));
    return { total_matches: hits.length, plans: hits.slice(0, limit).map(pub) };
  }
  if (name === "get_plan") {
    const r = rows.find((x) => x.pl_number === String(args.pl_number || "").trim());
    if (!r) throw new Error("plan not found");
    return pub(r);
  }
  if (name === "upcoming_objection_windows") {
    const days = clamp(args.days, 0, 365, 30);
    const start = args.as_of ? new Date(args.as_of + "T00:00:00Z") : new Date(new Date().toISOString().slice(0, 10) + "T00:00:00Z");
    if (Number.isNaN(+start) || (args.as_of && !/^\d{4}-\d{2}-\d{2}$/.test(args.as_of))) throw new Error("as_of must be YYYY-MM-DD");
    const out = [];
    for (const r of rows) {
      const end = new Date((r.objection_deadline_derived_60d_from_publication || "") + "T00:00:00Z");
      if (Number.isNaN(+end) || !(r.station_desc || "").includes("הפקדה")) continue;
      const left = Math.round((end - start) / 864e5);
      if (left >= 0 && left <= days) out.push({ ...pub(r), days_left_derived: left });
    }
    out.sort((a, b) => a.days_left_derived - b.days_left_derived || a.pl_number.localeCompare(b.pl_number));
    return { as_of: start.toISOString().slice(0, 10), note: NOTE, plans: out };
  }
  if (name === "data_status") return { generated: data.generated, plans: rows.length };
  throw new Error("unknown tool");
}

export function rpc(data, msg) {
  if (!msg || typeof msg !== "object" || Array.isArray(msg)) return { jsonrpc: "2.0", id: null, error: { code: -32600, message: "invalid request" } };
  const { id, method } = msg;
  if (id === undefined || id === null) return null;
  const ok = (result) => ({ jsonrpc: "2.0", id, result });
  if (method === "initialize") return ok({ protocolVersion: PROTOCOL, capabilities: { tools: {} }, serverInfo: { name: "ginot-hair-mcp", version: "0.1.0" } });
  if (method === "ping") return ok({});
  if (method === "tools/list") return ok({ tools: TOOLS });
  if (method === "tools/call") {
    try {
      const r = callTool(data, msg.params?.name, msg.params?.arguments || {});
      return ok({ content: [{ type: "text", text: JSON.stringify(r) }] });
    } catch (e) {
      return ok({ isError: true, content: [{ type: "text", text: String(e.message) }] });
    }
  }
  return { jsonrpc: "2.0", id, error: { code: -32601, message: "method not found" } };
}

const H = { "access-control-allow-origin": "*", "access-control-allow-headers": "content-type, mcp-protocol-version, mcp-session-id",
  "access-control-allow-methods": "POST, OPTIONS" };
const out = (body, status = 200) => new Response(body === null ? null : JSON.stringify(body),
  { status, headers: { ...H, "content-type": "application/json; charset=utf-8" } });

export async function handleRequest(request, fetchImpl = fetch) {
  if (request.method === "OPTIONS") return out(null, 204);
  if (request.method !== "POST") return out({ error: "POST JSON-RPC to /mcp; see README" }, 405);
  let msg;
  try { msg = await request.json(); } catch { return out({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "parse error" } }, 400); }
  const batch = Array.isArray(msg);
  if (batch && msg.length > 10) return out({ jsonrpc: "2.0", id: null, error: { code: -32600, message: "batch too large" } }, 400);
  let data;
  try {
    const r = await fetchImpl(new Request(ORIGIN, { cf: { cacheTtl: 300, cacheEverything: true } }));
    if (!r.ok) throw new Error("upstream " + r.status);
    data = await r.json();
  } catch { return out({ jsonrpc: "2.0", id: null, error: { code: -32603, message: "data temporarily unavailable" } }, 502); }
  const replies = (batch ? msg : [msg]).map((m) => rpc(data, m)).filter(Boolean);
  if (!replies.length) return out(null, 202);
  return out(batch ? replies : replies[0]);
}

export default { fetch: (request) => handleRequest(request) };
