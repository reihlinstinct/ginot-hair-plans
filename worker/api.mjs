// ginot-hair-api - read-only query layer over the static site data, plus an
// anonymous usage-stats counter (issue #821 part 2).
// Free Cloudflare Worker. Fetches the public data.json from GitHub Pages
// (edge-cached 5 min), filters per query params, CORS open.
// Privacy: /stats/event stores ONLY aggregate counters (event type + a
// dictionary-matched key or "other", per day) in Workers KV. No raw search
// text, no IP, no User-Agent, no user identification of any kind.
// Docs: https://reihlinstinct.github.io/ginot-hair-plans/about.html
import { securityTxtResponse } from "./securitytxt.mjs";
const ORIGIN = "https://reihlinstinct.github.io/ginot-hair-plans";
const CACHE_TTL = 300; // seconds, edge cache for the upstream data.json
const MAX_LIMIT = 500;
const DEFAULT_LIMIT = 100;

// Best-effort per-isolate rate limiting (fixed 1-minute window). Isolates are
// recycled, so this is a soft cap, not a guarantee - documented as such.
const RATE_LIMIT = 120; // requests per IP per window
const RATE_WINDOW_MS = 60_000;
const buckets = new Map();

function rateLimited(ip) {
  const now = Date.now();
  const b = buckets.get(ip);
  if (!b || now - b.start > RATE_WINDOW_MS) {
    buckets.set(ip, { start: now, n: 1 });
    return false;
  }
  b.n += 1;
  return b.n > RATE_LIMIT;
}

const ACTIVE_KEYS = ["הפקדה", "תנאים", "הכרעה", "בדיקה", "בהליך"]; // = site's ACTIVE_STATUSES
const isActive = (r) => ACTIVE_KEYS.some((k) => (r.station_desc || "").includes(k));

export function filterPlans(rows, p) {
  let out = rows;
  if (p.get("open") === "1") out = out.filter(isActive);
  const status = p.get("status");
  if (status) out = out.filter((r) => (r.station_desc || "").includes(status));
  const q = p.get("q");
  if (q) out = out.filter((r) => (r.pl_number || "").includes(q) || (r.pl_name || "").includes(q));
  const deadline = p.get("before"); // objection deadline on/before YYYY-MM-DD
  if (deadline) {
    out = out.filter((r) => {
      const d = r.objection_deadline_derived_60d_from_publication;
      return d && d <= deadline;
    });
  }
  return out;
}

export function filterPermits(permits, p) {
  let out = permits;
  const street = p.get("street");
  if (street) out = out.filter((r) => (r.address || "").includes(street));
  const status = p.get("status");
  if (status) out = out.filter((r) => (r.status || "").includes(status));
  const sug = p.get("type");
  if (sug) out = out.filter((r) => (r.sugbakasha || "").includes(sug));
  const q = p.get("q");
  if (q) out = out.filter((r) => (r.mispar_bakasha || "").includes(q) || (r.address || "").includes(q));
  return out;
}

function limitOf(p) {
  const n = parseInt(p.get("limit") || "", 10);
  if (!Number.isFinite(n) || n <= 0) return DEFAULT_LIMIT;
  return Math.min(n, MAX_LIMIT);
}

function json(body, { status = 200, headers = {} } = {}) {
  return new Response(JSON.stringify(body, null, 1), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "access-control-allow-origin": "*",
      "access-control-allow-methods": "GET, OPTIONS",
      "cache-control": `public, max-age=${CACHE_TTL}`,
      ...headers,
    },
  });
}


// --- Anonymous usage statistics (issue #821) -------------------------------
// Aggregate counters only. An event is {e, k}: e is one of EVENT_TYPES, k is
// either "other" or a value the client already matched against its own loaded
// data dictionary (a street name, plan number, or a closed-vocabulary filter
// name/value). Raw free text is never accepted: anything unmatched arrives as
// "other". Keys are per UTC day; nothing identifies a person.
const EVENT_TYPES = new Set(["search", "permits_search", "filter", "permits_filter"]);
const KEY_RE = /^[\w\u0590-\u05FF .'"()/:=+-]{1,60}$/u;
const STATS_PREFIX = "stats:v1:";
const STATS_DAYS = 30;

function dayKey(d) { return d.toISOString().slice(0, 10); }

async function recordStat(env, e, k) {
  // Best-effort: a KV failure (quota, outage) must never break the API.
  try {
    const key = STATS_PREFIX + dayKey(new Date()) + ":" + e + ":" + k;
    const cur = parseInt((await env.STATS.get(key)) || "0", 10) || 0;
    await env.STATS.put(key, String(cur + 1), { expirationTtl: (STATS_DAYS + 7) * 86400 });
    return true;
  } catch { return false; }
}

async function statsSummary(env) {
  const out = {}; // {e: {k: count}}
  let cursor;
  do {
    const page = await env.STATS.list({ prefix: STATS_PREFIX, cursor });
    cursor = page.list_complete ? undefined : page.cursor;
    for (const { name } of page.keys) {
      const rest = name.slice(STATS_PREFIX.length); // "<day>:<e>:<k>"
      const day = rest.slice(0, 10);
      const mid = rest.slice(11);
      const sep = mid.indexOf(":");
      if (sep < 0) continue;
      const e = mid.slice(0, sep), k = mid.slice(sep + 1);
      const v = parseInt((await env.STATS.get(name)) || "0", 10) || 0;
      (out[e] ||= {})[k] = ((out[e] ||= {})[k] || 0) + v;
    }
  } while (cursor);
  for (const e of Object.keys(out)) {
    out[e] = Object.fromEntries(
      Object.entries(out[e]).sort((a, b) => b[1] - a[1]).slice(0, 50));
  }
  return out;
}

const INDEX = {
  name: "ginot-hair-api",
  about: "שכבת שאילתות לקריאה בלבד מעל נתוני האתר הסטטיים של גינות העיר",
  endpoints: {
    "/plans": "תכניות. פרמטרים: open=1 (פתוחות בלבד), status, q, before=YYYY-MM-DD, limit",
    "/permits": "בקשות היתר. פרמטרים: street, status, type, q, limit",
    "/open": "תכניות פתוחות (כמו open.json הסטטי)",
    "/status": "תאריך עדכון ומונים",
    "/stats/event": "POST אירוע שימוש אנונימי {e, k} - מונים מצטברים בלבד, בלי טקסט חופשי ובלי IP",
    "/stats/summary": "מוני השימוש המצטברים (30 יום), ציבורי",
  },
  source: "https://github.com/reihlinstinct/ginot-hair-plans",
  docs: "https://reihlinstinct.github.io/ginot-hair-plans/about.html",
};

export async function handleRequest(request, fetchImpl = fetch, env = {}) {
  const sec = securityTxtResponse(request);
  if (sec) return sec;
  const url = new URL(request.url);
  if (request.method === "OPTIONS") {
    return json({}, { headers: { "access-control-allow-methods": "GET, POST, OPTIONS",
                                 "access-control-allow-headers": "content-type" } });
  }
  if (url.pathname === "/stats/event" && request.method === "POST") {
    if (!env.STATS) return json({ error: "stats not configured" }, { status: 503 });
    let body;
    try { body = await request.json(); } catch { return json({ error: "invalid JSON" }, { status: 400 }); }
    const e = String(body && body.e || "");
    const k = String(body && body.k || "");
    if (!EVENT_TYPES.has(e)) return json({ error: "unknown event type" }, { status: 400 });
    if (k !== "other" && !KEY_RE.test(k)) return json({ error: "invalid key" }, { status: 400 });
    const ok = await recordStat(env, e, k);
    return json({ recorded: ok }, { status: ok ? 202 : 500 });
  }
  if (url.pathname === "/stats/summary" && request.method === "GET") {
    if (!env.STATS) return json({ error: "stats not configured" }, { status: 503 });
    const stats = await statsSummary(env);
    return json({ days: STATS_DAYS, events: stats });
  }
  if (request.method !== "GET") return json({ error: "GET only" }, { status: 405 });
  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  if (rateLimited(ip)) return json({ error: "rate limit, retry shortly" }, { status: 429, headers: { "retry-after": "60" } });
  if (url.pathname === "/" || url.pathname === "") return json(INDEX);

  const upstream = new URL(
    url.pathname === "/open" ? "open.json" : "data.json", ORIGIN + "/");
  let resp;
  try {
    // Cache only successful upstream responses at the edge (a cached 404 for
    // a not-yet-published open.json would otherwise stick for CACHE_TTL).
    const cf = upstream.pathname.endsWith("data.json")
      ? { cacheTtl: CACHE_TTL, cacheEverything: true } : {};
    resp = await fetchImpl(new Request(upstream.toString(), { cf }));
  } catch (e) {
    return json({ error: "upstream fetch failed", detail: String(e && e.message || e) }, { status: 502 });
  }
  if (!resp.ok) return json({ error: "upstream unavailable", upstream_status: resp.status }, { status: 502 });
  const data = await resp.json();
  const p = url.searchParams;

  if (url.pathname === "/status") {
    return json({ generated: data.generated, plans: (data.rows || []).length,
                  permits: (data.permits || []).length });
  }
  if (url.pathname === "/open") {
    return json(data); // open.json already carries definition/count/plans
  }
  if (url.pathname === "/plans") {
    const rows = filterPlans(data.rows || [], p);
    const limit = limitOf(p);
    return json({ generated: data.generated, count: rows.length,
                  returned: Math.min(rows.length, limit), plans: rows.slice(0, limit) });
  }
  if (url.pathname === "/permits") {
    const permits = filterPermits(data.permits || [], p);
    const limit = limitOf(p);
    return json({ generated: data.generated, count: permits.length,
                  returned: Math.min(permits.length, limit), permits: permits.slice(0, limit) });
  }
  return json({ error: "unknown endpoint", endpoints: Object.keys(INDEX.endpoints) }, { status: 404 });
}

export default { fetch: (request, env) => handleRequest(request, fetch, env) };
