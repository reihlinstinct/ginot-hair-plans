// ginot-hair-api - read-only query layer over the static site data, plus an
// anonymous usage-stats counter (issue #821 part 2).
// Free Cloudflare Worker. Fetches the public data.json from GitHub Pages
// (edge-cached 5 min), filters per query params, CORS open.
// Privacy: /stats/event stores ONLY aggregate counters (event type + a
// dictionary-matched key or "other", per day) in Workers KV. Per-source
// totals (_by_src) use a closed set of caller tags (site/mirror/mcp/about/
// other), client-asserted or classified from Referer/Origin. No raw search
// text, no IP, no User-Agent, no user identification of any kind.
// Docs: https://reihlinstinct.github.io/ginot-hair-plans/about.html
import publicFields from "../src/ginot/static/public-api-fields.json" with { type: "json" };
import { securityTxtResponse } from "./securitytxt.mjs";
// Field names shared with the static publisher. No nested values pass through.
export function publicRows(rows, kind) {
  const fields = new Set(publicFields[kind] || []);
  return (Array.isArray(rows) ? rows : []).filter(r => r && typeof r === "object" && !Array.isArray(r))
    .map(r => Object.fromEntries(Object.entries(r).filter(([k, v]) => fields.has(k) &&
      (v === null || typeof v === "string" || typeof v === "boolean" ||
       (typeof v === "number" && Number.isFinite(v))))));
}
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
      const d = r.objection_deadline_verified || r.objection_deadline_derived_2m_from_publication;
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
  if (q) out = out.filter((r) => (r.tik_num || "").includes(q) || (r.address || "").includes(q));
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
// Aggregate counters only. An event is {e, k}: e is one of EVENT_TYPES and k
// is validated SERVER-SIDE against a dictionary rebuilt from the site's own
// public data.json (plan numbers/names, permit request numbers (tik_num), street names,
// and the closed status/type vocabulary). Any key not in the dictionary is
// recorded as "other": raw free text is never stored, so the public
// /stats/summary can never echo back something a visitor typed. Keys are per
// UTC day; no IP, no User-Agent, no user identification of any kind.
const EVENT_TYPES = new Set(["search", "permits_search", "filter", "permits_filter"]);
const KEY_RE = /^[\w\u0590-\u05FF .'"()/:=+-]{1,60}$/u;
const STATS_PREFIX = "stats:v1:";
// Closed set of caller tags for "who does what" stats (#991 follow-up):
// validated server-side like keys; anything else becomes "other".
const SRC_TYPES = new Set(["site", "mirror", "mcp", "about", "other"]);
const STATS_DAYS = 30;
const DICT_TTL_MS = 300_000; // rebuild the key dictionary at most every 5 min
const SUMMARY_MAX_KEYS = 500; // bound KV reads per summary call
const SUMMARY_CACHE_KEY = STATS_PREFIX + "summary-cache";
const SUMMARY_CACHE_TTL = 3600; // seconds; one KV list per hour per colo keeps the free list quota safe

function dayKey(d) { return d.toISOString().slice(0, 10); }

let dictCache = { ts: 0, keys: new Set() };

// Street names are the leading tokens of a permit address up to the first
// token containing a digit. The site client applies the same rule before
// sending a key; keep in sync with the dictionary code in src/ginot/page.py.
export function streetOf(address) {
  const tokens = String(address || "").trim().split(/\s+/);
  const out = [];
  for (const t of tokens) {
    if (/\d/.test(t)) break;
    out.push(t);
  }
  return out.join(" ");
}

// Allowed stat keys, rebuilt from the public data.json (edge-cached like the
// query endpoints, plus a short per-isolate cache). On any fetch failure the
// previous cache is kept; with no cache the set is empty and every key is
// recorded as "other" - validation never fails open.
async function keyDictionary(fetchImpl) {
  if (dictCache.keys.size && Date.now() - dictCache.ts < DICT_TTL_MS) return dictCache.keys;
  try {
    const resp = await fetchImpl(new Request(ORIGIN + "/data.json",
      { cf: { cacheTtl: CACHE_TTL, cacheEverything: true } }));
    if (resp.ok) {
      const data = await resp.json();
      const keys = new Set();
      for (const r of data.rows || []) {
        if (r.pl_number) keys.add(String(r.pl_number));
        if (r.pl_name) keys.add(String(r.pl_name));
        if (r.station_desc) keys.add(String(r.station_desc));
      }
      for (const r of data.permits || []) {
        const tik = r.tik_num || r.mispar_bakasha; // data.json uses tik_num
        if (tik) keys.add(String(tik));
        if (r.status) keys.add(String(r.status));
        if (r.sugbakasha) keys.add(String(r.sugbakasha));
        const st = streetOf(r.address);
        if (st) keys.add(st);
      }
      dictCache = { ts: Date.now(), keys };
    }
  } catch { /* keep the stale cache; empty cache fails closed below */ }
  return dictCache.keys;
}

// recordStat is gone: events are buffered by bumpEvent and written in the
// 15-min flush (see above), so a POST never touches KV synchronously.

// Per-source request counters ("who does what"), classified server-side into
// a closed set. src is client-asserted (anyone can claim "mirror"), so these
// are approximate usage stats, not attribution.
function classifySrc(request, explicit) {
  if (SRC_TYPES.has(explicit)) return explicit;
  const ref = request.headers.get("referer") || request.headers.get("origin") || "";
  // Browsers send origin-only Referer cross-origin, so no path heuristics
  // here: the about page tags itself with ?src=about instead.
  try {
    if (new URL(ref).hostname === "reihlinstinct.github.io") return "site";
  } catch { /* not a URL */ }
  return "other";
}

// In-isolate aggregation: a burst costs at most one flush per interval per
// isolate (~1 KV write per active source per interval), not one write per
// request, keeping the free plan's daily write quota safe. Best-effort:
// a failed flush drops counts but never fails the request.
const SRC_FLUSH_MS = 900_000; // 15 min: <=96 writes/source/day/isolate
// Pending counts are scoped per KV binding (prod has one binding per
// isolate; tests use separate fakes, so a shared Map would leak between
// them). JS Map keys here: the WeakMap key is the binding object.
const srcState = new WeakMap(); // STATS binding -> { pending, pendingEvents, lastFlush }
function srcStateFor(env) {
  let st = srcState.get(env.STATS);
  if (!st) { st = { pending: new Map(), pendingEvents: new Map(), chain: null, lastFlush: 0 }; srcState.set(env.STATS, st); }
  return st;
}
function bumpSrc(env, src) {
  if (!env.STATS) return;
  const st = srcStateFor(env);
  st.pending.set(src, (st.pending.get(src) || 0) + 1);
}
// Event counters are buffered in-isolate and written by the same 15-min
// flush as by_src: a per-event read-modify-write costs one KV read + one
// KV write per POST, and the free plan's daily write quota nearly breached
// on the first busy day. Buffering turns N posts into at most one
// read-modify-write per counter key per flush window, and a forced flush
// at FLUSH_PENDING_FORCE buffered EVENT counts bounds the burst loss:
// counts are lost only if the isolate is evicted before the next flush,
// at most FLUSH_PENDING_FORCE - 1 event counts per eviction - a bound
// that holds while no flush or summary is in progress; a long summary
// slot (one chain slot per list+get pass) lets the buffer grow past it
// until that slot ends.
const FLUSH_PENDING_FORCE = 25;
function bumpEvent(env, e, k) {
  if (!env.STATS) return false;
  const st = srcStateFor(env);
  const key = STATS_PREFIX + dayKey(new Date()) + ":" + e + ":" + k;
  st.pendingEvents.set(key, (st.pendingEvents.get(key) || 0) + 1);
  return true;
}
function pendingEventsTotal(st) {
  let n = 0;
  for (const c of st.pendingEvents.values()) n += c;
  return n;
}
// Flushes and summary reads run through one per-isolate promise chain, so
// a flush's read-modify-write can never overlap another flush, and a
// summary's KV reads + pending merge are one chain slot that no flush can
// interleave with. Without the chain, a forced flush can overlap a slower
// one (both read the same cur, the later put wins) and a summary can cache
// an undercount for the whole cache TTL.
function enqueueState(st, fn) {
  const run = (st.chain || Promise.resolve()).then(fn, fn);
  st.chain = run.catch(() => {});
  return run;
}
async function writeCount(env, key, n) {
  try {
    const cur = parseInt((await env.STATS.get(key)) || "0", 10) || 0;
    await env.STATS.put(key, String(cur + n), { expirationTtl: (STATS_DAYS + 7) * 86400 });
  } catch { /* dropped on a KV failure - approximate counters, as before */ }
}
async function flushSrc(env, force = false) {
  if (!env.STATS) return;
  const st = srcStateFor(env);
  if (st.pending.size === 0 && st.pendingEvents.size === 0) return;
  if (!force && Date.now() - st.lastFlush < SRC_FLUSH_MS) return;
  st.lastFlush = Date.now();
  await enqueueState(st, async () => {
    const day = dayKey(new Date());
    const entries = [...st.pending];
    st.pending.clear();
    const eventEntries = [...st.pendingEvents];
    st.pendingEvents.clear();
    const writes = [];
    for (const [key, n] of eventEntries) writes.push(writeCount(env, key, n));
    for (const [s, n] of entries) {
      writes.push(writeCount(env, STATS_PREFIX + day + ":_by_src:" + s, n));
    }
    await Promise.all(writes);
  });
}

async function statsSummary(env) {
  // Returns { ok, stats }; ok=false when the KV list failed, so the caller
  // must not cache a partial summary. KV reads AND the merge of this
  // isolate's pending counts run as one slot on the per-isolate chain, so
  // no flush can interleave between them: every count is either in the KV
  // values read here or still in pending, never in both or neither.
  const out = {}; // {e: {k: count}}
  const bySrc = {}; // {src: count} - underscore-prefixed control keys only
  const cutoff = dayKey(new Date(Date.now() - (STATS_DAYS - 1) * 86_400_000));
  let ok = true;
  await enqueueState(srcStateFor(env), async () => {
    let cursor, read = 0;
    try {
      do {
        const page = await env.STATS.list({ prefix: STATS_PREFIX, cursor });
        cursor = page.list_complete ? undefined : page.cursor;
        for (const { name } of page.keys) {
          if (++read > SUMMARY_MAX_KEYS) break;
          const rest = name.slice(STATS_PREFIX.length); // "<day>:<e>:<k>"
          if (!/^\d{4}-\d{2}-\d{2}:/.test(rest)) continue; // e.g. the summary cache key
          const day = rest.slice(0, 10);
          if (day < cutoff) continue; // KV TTL is STATS_DAYS+7; summary covers STATS_DAYS
          const mid = rest.slice(11);
          const sep = mid.indexOf(":");
          if (sep < 0) continue;
          const e = mid.slice(0, sep), k = mid.slice(sep + 1);
          const v = parseInt((await env.STATS.get(name)) || "0", 10) || 0;
          if (e === "_by_src") { bySrc[k] = (bySrc[k] || 0) + v; continue; }
          (out[e] ||= {})[k] = (out[e][k] || 0) + v;
        }
      } while (cursor && read <= SUMMARY_MAX_KEYS);
    } catch { ok = false; /* KV outage mid-list: return whatever was read so far */ }
    const st = srcStateFor(env); // merge this isolate's unflushed counts
    for (const [s, n] of st.pending) bySrc[s] = (bySrc[s] || 0) + n;
    for (const [key, n] of st.pendingEvents) {
      const rest = key.slice(STATS_PREFIX.length); // "<day>:<e>:<k>"
      const day = rest.slice(0, 10);
      if (day < cutoff) continue;
      const mid = rest.slice(11);
      const sep = mid.indexOf(":");
      if (sep < 0) continue;
      const e = mid.slice(0, sep), k = mid.slice(sep + 1);
      if (e === "_by_src") continue;
      (out[e] ||= {})[k] = (out[e][k] || 0) + n;
    }
  });
  for (const e of Object.keys(out)) {
    out[e] = Object.fromEntries(
      Object.entries(out[e]).sort((a, b) => b[1] - a[1]).slice(0, 50));
  }
  return { ok, stats: out, by_src: bySrc };
}

const INDEX = {
  name: "ginot-hair-api",
  about: "שכבת שאילתות לקריאה בלבד מעל נתוני האתר הסטטיים של גינות העיר",
  endpoints: {
    "/plans": "תכניות. פרמטרים: open=1 (פתוחות בלבד), status, q, before=YYYY-MM-DD, limit",
    "/permits": "בקשות היתר. פרמטרים: street, status, type, q, limit",
    "/open": "תכניות פתוחות (כמו open.json הסטטי)",
    "/status": "תאריך עדכון ומונים",
    "/stats/event": "POST אירוע שימוש אנונימי {e, k} - מונים מצטברים בלבד, בלי טקסט חופשי ובלי IP; recorded:true = התקבל ונשמר בזיכרון המקומי עד הכתיבה המרוכזת (עד ~15 דק')",
    "/stats/summary": "מוני השימוש המצטברים (30 יום), ציבורי",
  },
  source: "https://github.com/reihlinstinct/ginot-hair-plans",
  docs: "https://reihlinstinct.github.io/ginot-hair-plans/about.html",
};

export async function handleRequest(request, fetchImpl = fetch, env = {}, ctx = null) {
  const sec = securityTxtResponse(request);
  if (sec) return sec;
  const url = new URL(request.url);
  if (request.method === "OPTIONS") {
    return json({}, { headers: { "access-control-allow-methods": "GET, POST, OPTIONS",
                                 "access-control-allow-headers": "content-type" } });
  }
  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  if (rateLimited(ip)) return json({ error: "rate limit, retry shortly" }, { status: 429, headers: { "retry-after": "60" } });
  // Count every API caller, not only event senders: the mirror and MCP call
  // the GET endpoints without POSTing events, and the about page fetches
  // /stats/summary. GETs may pass ?src= (closed set); otherwise classify by
  // Referer/Origin, else "other". Aggregated in-isolate, flushed ~once/min.
  if (request.method === "GET") {
    bumpSrc(env, classifySrc(request, url.searchParams.get("src")));
    // Off the request path when the runtime gives us ctx (m5); tests await.
    if (ctx && ctx.waitUntil) ctx.waitUntil(flushSrc(env)); else await flushSrc(env);
  }
  if (url.pathname === "/stats/event" && request.method === "POST") {
    if (!env.STATS) return json({ error: "stats not configured" }, { status: 503 });
    let body;
    try { body = await request.json(); } catch { return json({ error: "invalid JSON" }, { status: 400 }); }
    const e = String(body && body.e || "");
    let k = String(body && body.k || "");
    const src = classifySrc(request, body && body.src);
    if (!EVENT_TYPES.has(e)) return json({ error: "unknown event type" }, { status: 400 });
    if (k !== "other" && !KEY_RE.test(k)) return json({ error: "invalid key" }, { status: 400 });
    if (k !== "other") {
      // Server-side enforcement of "no raw text": only keys that exist in the
      // site's own data dictionary are stored; everything else is "other".
      const dict = await keyDictionary(fetchImpl);
      if (!dict.has(k)) k = "other";
    }
    const ok = bumpEvent(env, e, k);
    bumpSrc(env, src);
    // Bound the burst loss: force a flush when the isolate already holds
    // FLUSH_PENDING_FORCE unwritten event counts, so eviction loses fewer.
    const flush = flushSrc(env, pendingEventsTotal(srcStateFor(env)) >= FLUSH_PENDING_FORCE);
    if (ctx && ctx.waitUntil) ctx.waitUntil(flush); else await flush;
    return json({ recorded: ok }, { status: ok ? 202 : 500 });
  }
  if (url.pathname === "/stats/summary" && request.method === "GET") {
    if (!env.STATS) return json({ error: "stats not configured" }, { status: 503 });
    // Cache the computed summary in a single KV key with a 1-hour TTL: an
    // uncached call lists every stats key in KV, and the free plan's daily
    // list quota is small (#990). KV (not the Cache API, which is a no-op on
    // workers.dev-only deployments) so the cache works on every request path.
    let body = null;
    try {
      const hit = await env.STATS.get(SUMMARY_CACHE_KEY);
      if (hit) body = JSON.parse(hit);
    } catch { /* corrupt/unreadable cache: recompute below */ }
    if (!body) {
      const { ok, stats, by_src } = await statsSummary(env);
      body = { days: STATS_DAYS, events: stats, by_src };
      if (ok) { // never cache a partial summary from a failed list
        try { await env.STATS.put(SUMMARY_CACHE_KEY, JSON.stringify(body),
                                  { expirationTtl: SUMMARY_CACHE_TTL }); } catch { /* best-effort */ }
      }
    }
    return json(body, { headers: { "cache-control": "public, max-age=900" } });
  }
  if (request.method !== "GET") return json({ error: "GET only" }, { status: 405 });
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
    const plans = publicRows(data.plans, "plans");
    return json({ generated: data.generated, definition: data.definition,
                  count: plans.length, plans });
  }
  if (url.pathname === "/plans") {
    const rows = filterPlans(publicRows(data.rows, "rows"), p);
    const limit = limitOf(p);
    return json({ generated: data.generated, count: rows.length,
                  returned: Math.min(rows.length, limit), plans: rows.slice(0, limit) });
  }
  if (url.pathname === "/permits") {
    const permits = filterPermits(publicRows(data.permits, "permits"), p);
    const limit = limitOf(p);
    return json({ generated: data.generated, count: permits.length,
                  returned: Math.min(permits.length, limit), permits: permits.slice(0, limit) });
  }
  return json({ error: "unknown endpoint", endpoints: Object.keys(INDEX.endpoints) }, { status: 404 });
}

export default { fetch: (request, env, ctx) => handleRequest(request, fetch, env, ctx) };
