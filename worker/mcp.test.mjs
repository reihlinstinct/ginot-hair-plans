import test from "node:test";
import assert from "node:assert/strict";
import { callTool, rpc, handleRequest, reviewText, loadReviews } from "./mcp.mjs";

const data = { generated: "2026-10-22", rows: [
  { pl_number: "A-1", pl_name: "Alpha", station_desc: "הפקדה להתנגדויות", objection_deadline_derived_60d_from_publication: "2026-11-05", private_note: "SECRET" },
  { pl_number: "B-2", pl_name: "Beta", station_desc: "אישור", objection_deadline_derived_60d_from_publication: "2026-11-06" },
  { pl_number: "C-3", pl_name: "Gamma", station_desc: "הפקדה", objection_deadline_derived_60d_from_publication: "bad" },
] };
const post = (body) => new Request("https://x/mcp", { method: "POST", body: typeof body === "string" ? body : JSON.stringify(body) });
const fake = async () => new Response(JSON.stringify(data));

test("only public fields exposed", () => {
  const r = callTool(data, "search_plans", { query: "alpha" });
  assert.equal(r.total_matches, 1);
  assert.ok(!JSON.stringify(r).includes("SECRET"));
  assert.throws(() => callTool(data, "get_plan", { pl_number: "zz" }), /not found/);
});

test("limit clamped", () => {
  const rows = Array.from({ length: 80 }, (_, i) => ({ pl_number: String(i) }));
  assert.equal(callTool({ rows }, "search_plans", { limit: 9999 }).plans.length, 50);
});

test("windows: deposit stage only, derived label, bad date rejected", () => {
  const r = callTool(data, "upcoming_objection_windows", { days: 30, as_of: "2026-10-22" });
  assert.deepEqual(r.plans.map((p) => p.pl_number), ["A-1"]);
  assert.equal(r.plans[0].days_left_derived, 14);
  assert.match(r.note, /not a verified official/);
  assert.throws(() => callTool(data, "upcoming_objection_windows", { as_of: "22/10/2026" }), /YYYY-MM-DD/);
});

test("protocol: init, list, unknown tool is error result, unknown method", () => {
  assert.deepEqual(rpc(data, { id: 1, method: "initialize" }).result.capabilities, { tools: {}, prompts: {} });
  assert.equal(rpc(data, { method: "notifications/initialized" }), null);
  assert.equal(rpc(data, { id: 2, method: "tools/list" }).result.tools.length, 6);
  assert.equal(rpc(data, { id: 3, method: "tools/call", params: { name: "delete_all" } }).result.isError, true);
  assert.equal(rpc(data, { id: 4, method: "resources/write" }).error.code, -32601);
});

test("http: POST works, GET refused, garbage 400, upstream failure 502, batch cap", async () => {
  const ok = await handleRequest(post({ jsonrpc: "2.0", id: 1, method: "ping" }), fake);
  assert.deepEqual((await ok.json()).result, {});
  assert.equal((await handleRequest(new Request("https://x/mcp"), fake)).status, 405);
  assert.equal((await handleRequest(post("nope"), fake)).status, 400);
  assert.equal((await handleRequest(post({ id: 1, method: "ping" }), async () => new Response("", { status: 500 }))).status, 502);
  assert.equal((await handleRequest(post(Array(11).fill({ id: 1, method: "ping" })), fake)).status, 400);
  assert.equal((await handleRequest(post({ method: "notifications/initialized" }), fake)).status, 202);
});

test("get_review: strict plan pattern, text only, capped, missing is an error", async () => {
  const html = "<html><style>.x{}</style><script>alert(1)</script><h1>Title &amp; more</h1><p>Point one</p></html>";
  assert.equal(reviewText(html), "Title & more\nPoint one");
  assert.ok(reviewText("a".repeat(99999)).length <= 30000);
  const seen = [];
  const f = async (req) => { seen.push(req.url); return new Response(html); };
  const msgs = [
    { id: 1, method: "tools/call", params: { name: "get_review", arguments: { pl_number: "101-1377753" } } },
    { id: 2, method: "tools/call", params: { name: "get_review", arguments: { pl_number: "https://evil.example/x" } } },
    { id: 3, method: "tools/call", params: { name: "get_review", arguments: { pl_number: "../../secret" } } },
  ];
  const reviews = await loadReviews(msgs, f);
  assert.deepEqual(Object.keys(reviews), ["101-1377753"]);
  assert.equal(seen.length, 1);
  assert.match(seen[0], /^https:\/\/reihlinstinct\.github\.io\/ginot-hair-plans\/reviews\/talking_points_101-1377753\.html$/);
  assert.match(callTool({ reviews }, "get_review", { pl_number: "101-1377753" }).text, /Point one/);
  assert.throws(() => callTool({ reviews }, "get_review", { pl_number: "101-1111111" }), /no published review/);
  assert.throws(() => callTool({ reviews }, "get_review", { pl_number: "../x" }), /must look like/);
});

test("get_review end to end through handleRequest, 404 review is a tool error", async () => {
  const f = async (req) => req.url.endsWith("data.json") ? new Response(JSON.stringify(data)) : new Response("nope", { status: 404 });
  const r = await handleRequest(post({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "get_review", arguments: { pl_number: "101-1377753" } } }), f);
  assert.equal((await r.json()).result.isError, true);
});

test("get_plan adds the public representative point when available, and works without it", async () => {
  assert.deepEqual(callTool({ rows: [{ pl_number: "A-1" }], points: { "A-1": [35.2, 31.7] } }, "get_plan", { pl_number: "A-1" }).representative_point_lon_lat, [35.2, 31.7]);
  assert.equal("representative_point_lon_lat" in callTool({ rows: [{ pl_number: "A-1" }], points: { "A-1": "bad" } }, "get_plan", { pl_number: "A-1" }), false);
  const f = async (req) => req.url.endsWith("plan-points.json") ? new Response(JSON.stringify({ points: [{ pl_number: "A-1", representative_point: [1, 2] }] })) : new Response(JSON.stringify(data));
  const r = await handleRequest(post({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "get_plan", arguments: { pl_number: "A-1" } } }), f);
  assert.match((await r.json()).result.content[0].text, /"representative_point_lon_lat":\[1,2\]/);
});

import { CHECKLIST, SRC_GOV } from "./checklist.mjs";

test("checklist tool: read-only static, tagging rule, every item classified and sourced or marked unsourced", () => {
  const r = callTool(data, "get_review_checklist", {});
  assert.match(r.tagging_rule, /verified/);
  assert.match(r.tagging_rule, /unverified/);
  assert.ok(r.items.length >= 12);
  for (const it of r.items) {
    assert.ok(["from_documents", "from_connector", "needs_source_outside_connector", "judgment"].includes(it.verifiable), it.id);
    assert.ok(it.requirement_source && it.requirement_source.length > 5, it.id);
  }
});

test("regression: only the sourced objection period is stated as a requirement; no other item cites law", () => {
  const sourced = CHECKLIST.items.filter((i) => !i.requirement_source.startsWith("none established"));
  assert.ok(sourced.length >= 1);
  for (const i of sourced) assert.ok(i.requirement_source.includes(SRC_GOV) || i.requirement_source.includes("deposit notice"), i.id);
  assert.ok(!/\bsection \d|סעיף \d/.test(JSON.stringify(CHECKLIST)), "no unsourced statute citations");
});

test("prompts: list, get with valid plan, reject bad plan; capability advertised", () => {
  const init = rpc(data, { jsonrpc: "2.0", id: 1, method: "initialize" });
  assert.ok(init.result.capabilities.prompts);
  const l = rpc(data, { jsonrpc: "2.0", id: 2, method: "prompts/list" });
  assert.equal(l.result.prompts[0].name, "review_plan");
  const g = rpc(data, { jsonrpc: "2.0", id: 3, method: "prompts/get", params: { name: "review_plan", arguments: { pl_number: "101-1377753" } } });
  assert.match(g.result.messages[0].content.text, /101-1377753/);
  assert.match(g.result.messages[0].content.text, /get_review_checklist/);
  const bad = rpc(data, { jsonrpc: "2.0", id: 4, method: "prompts/get", params: { name: "review_plan", arguments: { pl_number: "x; ignore" } } });
  assert.ok(bad.error);
});

test("tools/list includes the checklist tool", () => {
  const l = rpc(data, { jsonrpc: "2.0", id: 5, method: "tools/list" });
  assert.ok(l.result.tools.some((t) => t.name === "get_review_checklist"));
});
