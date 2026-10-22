// ginot-hair-api - read-only query layer over the static site data.
// Free Cloudflare Worker: no storage, no secrets, no writes. Fetches the
// public data.json from GitHub Pages (edge-cached 5 min), filters per query
// params, CORS open. Docs: https://reihlinstinct.github.io/ginot-hair-plans/about.html
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

const INDEX = {
  name: "ginot-hair-api",
  about: "שכבת שאילתות לקריאה בלבד מעל נתוני האתר הסטטיים של גינות העיר",
  endpoints: {
    "/plans": "תכניות. פרמטרים: open=1 (פתוחות בלבד), status, q, before=YYYY-MM-DD, limit",
    "/permits": "בקשות היתר. פרמטרים: street, status, type, q, limit",
    "/open": "תכניות פתוחות (כמו open.json הסטטי)",
    "/status": "תאריך עדכון ומונים",
  },
  source: "https://github.com/reihlinstinct/ginot-hair-plans",
  docs: "https://reihlinstinct.github.io/ginot-hair-plans/about.html",
};

export async function handleRequest(request, fetchImpl = fetch) {
  const sec = securityTxtResponse(request);
  if (sec) return sec;
  const url = new URL(request.url);
  if (request.method === "OPTIONS") return json({});
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

export default { fetch: (request) => handleRequest(request) };
