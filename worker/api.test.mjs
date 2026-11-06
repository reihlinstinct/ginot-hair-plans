import test from "node:test";
import assert from "node:assert/strict";
import { filterPlans, filterPermits, handleRequest, streetOf } from "./api.mjs";

const rows = [
  { pl_number: "101-1", pl_name: "שימור אבן שפרוט", station_desc: "הפקדה להתנגדויות/השגות",
    objection_deadline_derived_60d_from_publication: "2026-12-09" },
  { pl_number: "101-2", pl_name: "בניין מגורים", station_desc: "אישור" },
  { pl_number: "101-3", pl_name: "תוספת קומה", station_desc: "בבדיקה תכנונית",
    objection_deadline_derived_60d_from_publication: "2026-11-01" },
];
const permits = [
  { tik_num: "2024-1", address: "עמק רפאים 12 מושבה גרמנית", status: "בטיפול", sugbakasha: "דירה" },
  { tik_num: "2024-2", address: "לינקולן 5", status: "אושר", sugbakasha: "תוספת" },
];

test("filterPlans open=1 keeps only non-approved", () => {
  const out = filterPlans(rows, new URLSearchParams("open=1"));
  assert.deepEqual(out.map((r) => r.pl_number), ["101-1", "101-3"]);
});

test("filterPlans status/q/before", () => {
  assert.equal(filterPlans(rows, new URLSearchParams("status=הפקדה")).length, 1);
  assert.equal(filterPlans(rows, new URLSearchParams("q=שפרוט"))[0].pl_number, "101-1");
  assert.deepEqual(
    filterPlans(rows, new URLSearchParams("before=2026-11-30")).map((r) => r.pl_number),
    ["101-3"]);
});

test("filterPermits street/status/type", () => {
  assert.equal(filterPermits(permits, new URLSearchParams("street=רפאים"))[0].tik_num, "2024-1");
  assert.equal(filterPermits(permits, new URLSearchParams("status=אושר"))[0].tik_num, "2024-2");
  assert.equal(filterPermits(permits, new URLSearchParams("type=דירה")).length, 1);
});

const stub = () => Promise.resolve(new Response(
  JSON.stringify({ generated: "2026-10-21", rows, permits }), { status: 200 }));

test("handleRequest /plans?open=1 end-to-end with stubbed upstream", async () => {
  const resp = await handleRequest(new Request("https://x.workers.dev/plans?open=1"), stub);
  assert.equal(resp.headers.get("access-control-allow-origin"), "*");
  const body = await resp.json();
  assert.equal(body.count, 2);
  assert.equal(body.generated, "2026-10-21");
});

test("handleRequest /status and unknown route", async () => {
  const s = await (await handleRequest(new Request("https://x.workers.dev/status"), stub)).json();
  assert.deepEqual(s, { generated: "2026-10-21", plans: 3, permits: 2 });
  const nf = await handleRequest(new Request("https://x.workers.dev/nope"), stub);
  assert.equal(nf.status, 404);
});

// --- Anonymous usage stats (issue #821) -------------------------------------
function fakeKv() {
  const m = new Map();
  return {
    async get(k) { return m.has(k) ? m.get(k) : null; },
    async put(k, v) { m.set(k, v); },
    async list({ prefix }) {
      return { list_complete: true,
               keys: [...m.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })) };
    },
  };
}

test("/stats/event validates keys server-side against the data dictionary", async () => {
  const env = { STATS: fakeKv() };
  const post = (b) => new Request("https://x.workers.dev/stats/event",
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(b) });
  // Dictionary from the stubbed data.json: plan name "שימור אבן שפרוט",
  // street "עמק רפאים", mispar "2024-1", statuses, types.
  assert.equal((await handleRequest(post({ e: "search", k: "שימור אבן שפרוט" }), stub, env)).status, 202);
  assert.equal((await handleRequest(post({ e: "permits_search", k: "עמק רפאים" }), stub, env)).status, 202);
  assert.equal((await handleRequest(post({ e: "search", k: "other" }), stub, env)).status, 202);
  // Free text that is NOT in the dictionary is coerced to "other", never stored raw.
  assert.equal((await handleRequest(post({ e: "search", k: "משה לוי 0501234567" }), stub, env)).status, 202);
  assert.equal((await handleRequest(post({ e: "hack", k: "x" }), stub, env)).status, 400);
  assert.equal((await handleRequest(post({ e: "search", k: "x".repeat(61) }), stub, env)).status, 400);
  assert.equal((await handleRequest(post({ e: "search", k: "bad<script>" }), stub, env)).status, 400);
  const sum = await (await handleRequest(new Request("https://x.workers.dev/stats/summary"), stub, env)).json();
  assert.equal(sum.events.search["שימור אבן שפרוט"], 1);
  assert.equal(sum.events.permits_search["עמק רפאים"], 1);
  assert.equal(sum.events.search.other, 2); // the explicit "other" + coerced free text
  assert.ok(!sum.events.search["משה לוי 0501234567"]);
});

test("/stats/event returns 500 when the KV write fails", async () => {
  const env = { STATS: {
    async get() { throw new Error("kv down"); },
    async put() { throw new Error("kv down"); },
    async list() { return { list_complete: true, keys: [] }; },
  } };
  const r = await handleRequest(new Request("https://x.workers.dev/stats/event",
    { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ e: "search", k: "other" }) }), stub, env);
  assert.equal(r.status, 500);
  assert.deepEqual(await r.json(), { recorded: false });
});

test("/stats/summary covers only the last 30 days, not the 37-day TTL", async () => {
  const kv = fakeKv();
  await kv.put("stats:v1:2000-01-01:search:old", "7"); // far outside the window
  const today = new Date().toISOString().slice(0, 10);
  await kv.put("stats:v1:" + today + ":search:new", "3");
  const sum = await (await handleRequest(new Request("https://x.workers.dev/stats/summary"), stub, { STATS: kv })).json();
  assert.equal(sum.events.search.new, 3);
  assert.equal(sum.events.search.old, undefined);
  assert.equal(sum.days, 30);
});

test("/stats/summary tolerates a KV list failure", async () => {
  const env = { STATS: {
    async get() { return null; },
    async put() {},
    async list() { throw new Error("kv down"); },
  } };
  const r = await handleRequest(new Request("https://x.workers.dev/stats/summary"), stub, env);
  assert.equal(r.status, 200);
  assert.deepEqual((await r.json()).events, {});
});

test("OPTIONS preflight allows POST with content-type", async () => {
  const r = await handleRequest(new Request("https://x.workers.dev/stats/event", { method: "OPTIONS" }), stub, {});
  assert.equal(r.status, 200);
  assert.match(r.headers.get("access-control-allow-methods"), /POST/);
  assert.match(r.headers.get("access-control-allow-headers"), /content-type/);
});

test("stats endpoints are rate limited like the query endpoints", async () => {
  const env = { STATS: fakeKv() };
  const ip = "203.0.113.99";
  const mk = () => new Request("https://x.workers.dev/stats/event",
    { method: "POST", headers: { "content-type": "application/json", "cf-connecting-ip": ip },
      body: JSON.stringify({ e: "search", k: "other" }) });
  let last;
  for (let i = 0; i < 120; i++) last = await handleRequest(mk(), stub, env);
  assert.equal(last.status, 202);
  assert.equal((await handleRequest(mk(), stub, env)).status, 429);
});

test("/stats/event without KV returns 503; POST to other routes still 405", async () => {
  const r = await handleRequest(new Request("https://x.workers.dev/stats/event",
    { method: "POST", body: "{}" }), fetch, {});
  assert.equal(r.status, 503);
  const r2 = await handleRequest(new Request("https://x.workers.dev/plans", { method: "POST" }), fetch, {});
  assert.equal(r2.status, 405);
});

test("streetOf strips house numbers (the shared client/server street rule)", () => {
  assert.equal(streetOf("עמק רפאים 12 מושבה גרמנית"), "עמק רפאים");
  assert.equal(streetOf("לינקולן 5"), "לינקולן");
  assert.equal(streetOf(""), "");
});

// The upstream may drift: every query route must retain the privacy boundary.
test("query routes never echo unknown private or nested fields", async () => {
  const secret = "SYNTHETIC_PRIVATE_SENTINEL";
  const privateFields = { planner_note: secret, phone: secret, national_id: secret,
    baaleiInyanList: [secret], tracking_state: secret, future_private: secret };
  const unsafe = () => Promise.resolve(new Response(JSON.stringify({
    generated: "2026-11-06", definition: "public", count: 1,
    rows: [{ ...rows[0], ...privateFields, land_status: { secret } }],
    permits: [{ ...permits[0], ...privateFields, status: [secret] }],
    plans: [{ ...rows[0], ...privateFields, pl_area_dunam: { secret } }],
    future_private: secret,
  })));
  for (const route of ["/plans", "/permits", "/open"]) {
    const resp = await handleRequest(new Request("https://x.workers.dev" + route), unsafe);
    assert.equal(resp.status, 200);
    const text = await resp.text();
    assert.ok(!text.includes(secret), route);
    assert.ok(text.includes(route === "/permits" ? "2024-1" : "101-1"));
  }
});

test("/open count matches sanitized public plan rows", async () => {
  const unsafe = () => Promise.resolve(new Response(JSON.stringify({
    generated: "2026-11-06", count: 4,
    plans: [null, "malformed", [], { pl_number: "101-1" }],
  })));
  const resp = await handleRequest(new Request("https://x.workers.dev/open"), unsafe);
  const data = await resp.json();
  assert.equal(data.count, data.plans.length);
  assert.equal(data.count, 1);
  assert.deepEqual(data.plans, [{ pl_number: "101-1" }]);
});
