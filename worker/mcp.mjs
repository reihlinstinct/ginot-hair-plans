// ginot-hair-mcp - hosted read-only MCP (Streamable HTTP, stateless JSON replies).
// Free Cloudflare Worker: no secrets, no bindings, no write tools. Reads only the
// public data.json on GitHub Pages. Objection dates are DERIVED, not official.
import { filterPlans } from "./api.mjs";
import { CHECKLIST, PROMPT, promptText } from "./checklist.mjs";
import { securityTxtResponse } from "./securitytxt.mjs";
const ORIGIN = "https://reihlinstinct.github.io/ginot-hair-plans/data.json";
const POINTS_URL = "https://reihlinstinct.github.io/ginot-hair-plans/plan-points.json";
const REVIEW_BASE = "https://reihlinstinct.github.io/ginot-hair-plans/reviews/talking_points_";
const PL_RE = /^\d{3}-\d{7}$/;
const MAX_REVIEW = 30000;
const PROTOCOL = "2024-11-05";
const NOTE = "Derived from publication dates (two calendar months, s.102); not a verified official deadline. Check the plan's source page.";
const FIELDS = ["pl_number", "pl_name", "station_desc", "internet_short_status", "entity_subtype_desc",
  "receiving_date", "open_date", "depositing_date", "pl_last_deposit_date",
  "objection_deadline_derived_2m_from_publication", "objection_deadline_derived_60d_from_publication", "pl_area_dunam", "mavat_url",
  "last_update_date", "land_status", "land_status_date"];
const pub = (r, pts) => {
  const o = Object.fromEntries(FIELDS.filter((k) => k in r).map((k) => [k, r[k]]));
  const pt = pts?.[r.pl_number];
  if (Array.isArray(pt) && pt.length === 2 && pt.every(Number.isFinite)) o.representative_point_lon_lat = pt;
  return o;
};
const clamp = (v, lo, hi, d) => Math.min(Math.max(Number.isFinite(+v) ? Math.trunc(+v) : d, lo), hi);

// Hebrew search folding for search_plans. A token with a digit, a hyphen or a
// Latin letter is never folded (plan numbers, English names): it only ever
// matches itself, exactly. Otherwise up to 2 leading prefix letters
// (ו ה ב כ ל מ ש - the one-letter conjunction/preposition/article set) are
// stripped, and the plural endings ים (dropped) and ות (either dropped or
// turned into ה, since that is the matching feminine singular ending) are
// tried on both the original and the prefix-stripped form. A folded variant
// is only kept with 3 or more letters left, so short cores never cause a
// false match (e.g. "גני" must not fold-match "עוגנים": the stripped form is
// "עוגן", not "גני", and "גני" itself has no prefix letter to strip).
const FOLD_PREFIX = new Set(["ו", "ה", "ב", "כ", "ל", "מ", "ש"]);
const NON_FOLDABLE = /[0-9\-A-Za-z]/;
const tokenize = (text) => String(text).toLowerCase().split(/\s+/).filter(Boolean);

function foldVariants(token) {
  if (NON_FOLDABLE.test(token)) return new Set([token]);
  let i = 0;
  while (i < 2 && i < token.length && FOLD_PREFIX.has(token[i])) i++;
  const bases = i > 0 ? [token, token.slice(i)] : [token];
  const out = new Set();
  for (const base of bases) {
    out.add(base);
    if (base.endsWith("ים")) out.add(base.slice(0, -2));
    if (base.endsWith("ות")) { out.add(base.slice(0, -2) + "ה"); out.add(base.slice(0, -2)); }
  }
  const kept = new Set([...out].filter((v) => v.length >= 3));
  return kept.size ? kept : new Set([token]);
}

// null = no match; "exact" = identical token; "folded" = share a folded variant.
function tokenMatch(queryToken, targetToken, fold) {
  if (queryToken === targetToken) return "exact";
  if (!fold) return null;
  const targetVariants = foldVariants(targetToken);
  for (const v of foldVariants(queryToken)) if (targetVariants.has(v)) return "folded";
  return null;
}

const SEARCH_FIELDS = ["pl_number", "pl_name", "station_desc", "entity_subtype_desc"];

// A row matches only if every query token matches some token in the row (any
// order - a bag-of-words match, same as the plain substring search it
// replaces could cross word boundaries). The row's overall tier is "exact"
// only when every query token matched exactly; one folded token downgrades
// the whole row to "folded", which only fills slots left after exact rows.
function matchRow(row, queryTokens, fold) {
  const targetTokens = SEARCH_FIELDS.flatMap((k) => tokenize(row[k] || ""));
  const matchedAs = [];
  let tier = "exact";
  for (const qt of queryTokens) {
    let best = null, bestTarget = null;
    for (const tt of targetTokens) {
      const m = tokenMatch(qt, tt, fold);
      if (m === "exact") { best = "exact"; bestTarget = tt; break; }
      if (m === "folded" && !best) { best = "folded"; bestTarget = tt; }
    }
    if (!best) return null;
    matchedAs.push(bestTarget);
    if (best !== "exact") tier = "folded";
  }
  return { tier, matchedAs };
}

export const TOOLS = [
  { name: "search_plans", description: "Search public plans by text in number/name/status/type. " +
      "Exact whole-token matches rank first; Hebrew-folded whole-token matches (stripped prefix letters/plural endings) fill " +
      "next; partial substring matches (the query text found anywhere in the row, the old pre-folding search behavior) fill " +
      "remaining slots up to limit, so results are always a superset of a plain substring search. Each result carries " +
      "match: \"exact\"|\"folded\"|\"partial\" and matched_as. Pass fold:false to skip the folded tier (exact whole-token " +
      "plus partial substring matches only).",
    inputSchema: { type: "object", properties: { query: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 50 },
      fold: { type: "boolean", description: "Default true. false skips the Hebrew-folded tier: exact whole-token and partial substring matches only." } } } },
  { name: "get_plan", description: "Get one public plan by pl_number.",
    inputSchema: { type: "object", properties: { pl_number: { type: "string" } }, required: ["pl_number"] } },
  { name: "upcoming_objection_windows", description: "Deposit-stage plans whose DERIVED objection window ends within N days. " + NOTE,
    inputSchema: { type: "object", properties: { days: { type: "integer", minimum: 0, maximum: 365 }, as_of: { type: "string", description: "YYYY-MM-DD" } } } },
  { name: "get_review", description: "Plain text of the already-published AI review (talking points, source-tagged) for one plan, if one exists on the public site. Not an official document; check the plan's source page.",
    inputSchema: { type: "object", properties: { pl_number: { type: "string", description: "e.g. 101-1377753" } }, required: ["pl_number"] } },
  { name: "get_review_checklist", description: "What to check before a plan review is finished: document completeness, objection window and notices, area/rights consistency, setbacks/heights/parking, preservation, unexplained changes. Each item says whether it is verifiable from documents and where its requirement is sourced. Includes the verified/unverified tagging rule. Static, public, read-only.",
    inputSchema: { type: "object", properties: {} } },
  { name: "data_status", description: "Dataset generation date and plan count.", inputSchema: { type: "object", properties: {} } },
];

export function callTool(data, name, args = {}) {
  const rows = data.rows || [];
  if (name === "search_plans") {
    const limit = clamp(args.limit, 1, 50, 20);
    const queryTokens = tokenize(args.query || "");
    if (!queryTokens.length) return { total_matches: rows.length, plans: rows.slice(0, limit).map(pub) };
    const fold = args.fold !== false;
    const exactHits = [], foldedHits = [], partialHits = [];
    for (const r of rows) {
      const m = matchRow(r, queryTokens, fold);
      if (m) { (m.tier === "exact" ? exactHits : foldedHits).push({ row: r, matchedAs: m.matchedAs }); continue; }
      // Not an exact or folded whole-token match: fall back to the old plain substring
      // behavior so the result set is always a superset of it. A row is a "partial" hit
      // when every query token appears anywhere in the joined searchable text (not
      // necessarily as its own token) - e.g. "1348069" inside the token "101-1348069",
      // or "גינ" inside a longer word. Every row lands in exactly one tier (exact,
      // folded or partial), so there is no duplicate across tiers.
      const rowText = SEARCH_FIELDS.map((k) => String(r[k] || "")).join(" ").toLowerCase();
      if (queryTokens.every((qt) => rowText.includes(qt))) partialHits.push({ row: r, matchedAs: queryTokens.slice() });
    }
    const ordered = [...exactHits.map((h) => ({ ...h, tier: "exact" })), ...foldedHits.map((h) => ({ ...h, tier: "folded" })),
      ...partialHits.map((h) => ({ ...h, tier: "partial" }))];
    return {
      total_matches: ordered.length,
      plans: ordered.slice(0, limit).map(({ row, matchedAs, tier }) => ({ ...pub(row), match: tier, matched_as: matchedAs })),
    };
  }
  if (name === "get_plan") {
    const r = rows.find((x) => x.pl_number === String(args.pl_number || "").trim());
    if (!r) throw new Error("plan not found");
    return pub(r, data.points);
  }
  if (name === "upcoming_objection_windows") {
    const days = clamp(args.days, 0, 365, 30);
    const start = args.as_of ? new Date(args.as_of + "T00:00:00Z") : new Date(new Date().toISOString().slice(0, 10) + "T00:00:00Z");
    if (Number.isNaN(+start) || (args.as_of && !/^\d{4}-\d{2}-\d{2}$/.test(args.as_of))) throw new Error("as_of must be YYYY-MM-DD");
    const out = [];
    for (const r of rows) {
      const end = new Date((r.objection_deadline_derived_2m_from_publication || "") + "T00:00:00Z");
      if (Number.isNaN(+end) || !(r.station_desc || "").includes("הפקדה")) continue;
      const left = Math.round((end - start) / 864e5);
      if (left >= 0 && left <= days) out.push({ ...pub(r), days_left_derived: left });
    }
    out.sort((a, b) => a.days_left_derived - b.days_left_derived || a.pl_number.localeCompare(b.pl_number));
    return { as_of: start.toISOString().slice(0, 10), note: NOTE, plans: out };
  }
  if (name === "get_review") {
    const pl = String(args.pl_number || "").trim();
    if (!PL_RE.test(pl)) throw new Error("pl_number must look like 101-1234567");
    const text = data.reviews?.[pl];
    if (!text) throw new Error("no published review for this plan");
    return { pl_number: pl, source: "published AI review page on the public site; not an official document", text };
  }
  if (name === "get_review_checklist") return CHECKLIST;
  if (name === "data_status") return { generated: data.generated, plans: rows.length };
  throw new Error("unknown tool");
}

export function reviewText(html) {
  const t = String(html).replace(/<(style|script)[\s\S]*?<\/\1>/gi, " ").replace(/<[^>]+>/g, "\n")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, " ").replace(/\n\s*\n+/g, "\n").trim();
  return t.slice(0, MAX_REVIEW);
}

// Only get_review calls trigger a fetch, and only for a strictly validated plan number.
export async function loadReviews(msgs, fetchImpl) {
  const reviews = {};
  for (const m of msgs) {
    const a = m?.method === "tools/call" && m.params?.name === "get_review" ? m.params.arguments : null;
    const pl = String(a?.pl_number ?? "").trim();
    if (!PL_RE.test(pl) || pl in reviews) continue;
    try {
      const r = await fetchImpl(new Request(REVIEW_BASE + pl + ".html", { cf: { cacheTtl: 300, cacheEverything: true } }));
      if (r.ok) reviews[pl] = reviewText(await r.text());
    } catch { /* no review */ }
  }
  return reviews;
}

export function rpc(data, msg) {
  if (!msg || typeof msg !== "object" || Array.isArray(msg)) return { jsonrpc: "2.0", id: null, error: { code: -32600, message: "invalid request" } };
  const { id, method } = msg;
  if (id === undefined || id === null) return null;
  const ok = (result) => ({ jsonrpc: "2.0", id, result });
  if (method === "initialize") return ok({ protocolVersion: PROTOCOL, capabilities: { tools: {}, prompts: {} }, serverInfo: { name: "ginot-hair-mcp", version: "0.1.0" } });
  if (method === "ping") return ok({});
  if (method === "tools/list") return ok({ tools: TOOLS });
  if (method === "prompts/list") return ok({ prompts: [PROMPT] });
  if (method === "prompts/get") {
    const pl = String(msg.params?.arguments?.pl_number ?? "").trim();
    if (msg.params?.name !== PROMPT.name || !PL_RE.test(pl)) return { jsonrpc: "2.0", id, error: { code: -32602, message: "unknown prompt or bad pl_number" } };
    return ok({ description: PROMPT.description, messages: [{ role: "user", content: { type: "text", text: promptText(pl) } }] });
  }
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
  const sec = securityTxtResponse(request);
  if (sec) return sec;
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
  if ((batch ? msg : [msg]).slice(0, 10).some((m) => m?.method === "tools/call" && m.params?.name === "get_plan")) {
    try {
      const r = await fetchImpl(new Request(POINTS_URL, { cf: { cacheTtl: 300, cacheEverything: true } }));
      if (r.ok) data.points = Object.fromEntries(((await r.json()).points || []).map((p) => [p.pl_number, p.representative_point]));
    } catch { /* coordinates are optional */ }
  }
  data.reviews = await loadReviews((batch ? msg : [msg]).slice(0, 10), fetchImpl);
  const replies = (batch ? msg : [msg]).map((m) => rpc(data, m)).filter(Boolean);
  if (!replies.length) return out(null, 202);
  return out(batch ? replies : replies[0]);
}

export default { fetch: (request) => handleRequest(request) };
