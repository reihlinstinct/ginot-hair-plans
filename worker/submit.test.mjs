import test from "node:test";
import assert from "node:assert/strict";
import { validate, submit, rpc, handleRequest, LIMITS, _state } from "./submit.mjs";

const ENV = { SUBMIT_KEY: "k1", GITHUB_TOKEN: "tok", INBOX_REPO: "o/inbox", DISABLED: "0" };
const GOOD = { pl_number: "101-1", review: "x".repeat(60), agent_name: "Test Bot-1", key: "k1" };
function mock({ open = [], inboxOk = true } = {}) {
  const calls = [];
  const f = async (url, init = {}) => {
    calls.push({ url: String(url), method: init.method || "GET", body: init.body, auth: init.headers?.authorization });
    if (String(url).endsWith("data.json")) return new Response(JSON.stringify({ rows: [{ pl_number: "101-1" }, { pl_number: "101-2" }] }));
    if (String(url).endsWith("permit-ids.json")) return new Response(JSON.stringify({ ids: ["2026/0439.00", "2025/0100.01"] }));
    if (!inboxOk) return new Response("{}", { status: 500 });
    if ((init.method || "GET") === "GET") return new Response(JSON.stringify(open));
    return new Response("{}", { status: 201 });
  };
  return { f, calls };
}
const reset = () => { _state.ip.clear(); _state.day = { key: "", n: 0 }; };

test("validate: plan, length, links/html, name", () => {
  const plans = new Set(["101-1"]);
  assert.equal(validate({ ...GOOD, pl_number: "nope" }, plans), "unknown plan");
  assert.equal(validate({ ...GOOD, review: "short" }, plans), "review too short");
  assert.equal(validate({ ...GOOD, review: "x".repeat(LIMITS.maxChars + 1) }, plans), "review too long");
  for (const bad of ["see https://evil.example now " + "x".repeat(40), "<script>" + "x".repeat(50), "[a](b) " + "x".repeat(50), "mail me a@b.co " + "x".repeat(50)])
    assert.match(validate({ ...GOOD, review: bad }, plans), /not allowed/);
  assert.match(validate({ ...GOOD, agent_name: "bad<name>" }, plans), /agent_name/);
  assert.equal(validate(GOOD, plans).pl, "101-1");
});

test("regression: submission only opens a labelled quarantined issue, never writes data", async () => {
  reset();
  const { f, calls } = mock();
  const r = await submit(ENV, GOOD, "1.1.1.1", f);
  assert.equal(r.status, "received");
  const writes = calls.filter((c) => c.method !== "GET");
  assert.equal(writes.length, 1);
  assert.match(writes[0].url, /api\.github\.com\/repos\/o\/inbox\/issues$/);
  assert.ok(!calls.some((c) => /ginot-hair-plans/.test(c.url) && c.method !== "GET"));
  const issue = JSON.parse(writes[0].body);
  assert.deepEqual(issue.labels, ["external-review"]);
  assert.match(issue.body, /UNTRUSTED external AI review/);
});

test("wrong or missing key rejected before any GitHub call", async () => {
  reset();
  const { f, calls } = mock();
  assert.equal((await submit(ENV, { ...GOOD, key: "bad" }, "2.2.2.2", f)).error, "invalid key");
  assert.equal((await submit({ ...ENV, SUBMIT_KEY: "" }, { ...GOOD, key: "" }, "2.2.2.2", f)).error, "invalid key");
  assert.equal(calls.length, 0);
});

test("kill switch disables submissions", async () => {
  reset();
  const { f, calls } = mock();
  assert.match((await submit({ ...ENV, DISABLED: "1" }, GOOD, "3.3.3.3", f)).error, /disabled/);
  assert.equal(calls.length, 0);
});

test("one pending per plan", async () => {
  reset();
  const { f } = mock({ open: [{ title: "[external-review] 101-1" }] });
  assert.match((await submit(ENV, GOOD, "4.4.4.4", f)).error, /already pending/);
});

test("per-IP hourly limit", async () => {
  reset();
  const { f } = mock();
  let last;
  for (let i = 0; i < LIMITS.perIpHour + 1; i++) last = await submit(ENV, GOOD, "5.5.5.5", f);
  assert.match(last.error, /rate limit/);
});

test("inbox failure is reported, not published", async () => {
  reset();
  const { f } = mock({ inboxOk: false });
  assert.equal((await submit(ENV, GOOD, "6.6.6.6", f)).error, "inbox unavailable");
});

test("mcp protocol and http guards", async () => {
  reset();
  const { f } = mock();
  assert.equal((await rpc(ENV, { id: 1, method: "tools/list" }, "7.7.7.7", f)).result.tools[0].name, "submit_review");
  assert.equal((await rpc(ENV, { id: 2, method: "tools/call", params: { name: "delete" } }, "7.7.7.7", f)).result.isError, true);
  const post = (b) => new Request("https://x/", { method: "POST", body: b });
  assert.equal((await handleRequest(post("x".repeat(9000)), ENV, f)).status, 413);
  assert.equal((await handleRequest(post("nope"), ENV, f)).status, 400);
  assert.equal((await handleRequest(post("[]"), ENV, f)).status, 400);
  assert.equal((await handleRequest(new Request("https://x/"), ENV, f)).status, 405);
});

test("key field description says where the public key lives", async () => {
  const { TOOL } = await import("./submit.mjs");
  const d = TOOL.inputSchema.properties.key.description;
  assert.match(d, /worker\/README\.md/);
  assert.match(d, /https:\/\/github\.com\/reihlinstinct\/ginot-hair-plans/);
  assert.ok(!/gh-submit-/.test(d), "the value itself is not embedded");
});

// #515: permit requests (tik_num) as a review target.
const PERMIT = { tik_num: "2026/0439.00", review: "y".repeat(60), agent_name: "Test Bot-1", key: "k1" };

test("validate: exactly one target, permit ids checked against the published list", () => {
  const plans = new Set(["101-1"]), permits = new Set(["2026/0439.00"]);
  assert.equal(validate({ ...GOOD, tik_num: "2026/0439.00" }, plans, permits), "give pl_number or tik_num, not both");
  assert.equal(validate({ review: GOOD.review, agent_name: "a", key: "k1" }, plans, permits), "pl_number or tik_num is required");
  assert.equal(validate({ ...PERMIT, tik_num: "2026/9999.00" }, plans, permits), "unknown permit request");
  assert.equal(validate({ ...PERMIT, tik_num: "2026/0439" }, plans, new Set(["2026/0439"])), "unknown permit request");
  assert.equal(validate({ ...PERMIT, tik_num: "101-1" }, plans, permits), "unknown permit request");
  const v = validate(PERMIT, plans, permits);
  assert.equal(v.kind, "permit");
  assert.equal(v.id, "2026/0439.00");
  assert.equal(v.pl, undefined);
  assert.equal(validate(GOOD, plans, permits).kind, "plan");
});

test("permit submission opens a quarantined issue titled by tik_num and fetches only the permit list", async () => {
  reset();
  const { f, calls } = mock();
  const r = await submit(ENV, PERMIT, "8.8.8.8", f);
  assert.equal(r.status, "received");
  assert.ok(calls.some((c) => c.url.endsWith("permit-ids.json")));
  assert.ok(!calls.some((c) => c.url.endsWith("data.json")));
  const issue = JSON.parse(calls.find((c) => c.method === "POST").body);
  assert.equal(issue.title, "[external-review] permit 2026/0439.00");
  assert.deepEqual(issue.labels, ["external-review"]);
  assert.match(issue.body, /Permit request: 2026\/0439\.00/);
  assert.match(issue.body, /UNTRUSTED external AI review/);
});

test("plan submission still fetches only data.json", async () => {
  reset();
  const { f, calls } = mock();
  assert.equal((await submit(ENV, GOOD, "9.9.9.9", f)).status, "received");
  assert.ok(!calls.some((c) => c.url.endsWith("permit-ids.json")));
});

test("one pending per permit request; a plan with the same digits does not collide", async () => {
  reset();
  const { f } = mock({ open: [{ title: "[external-review] permit 2026/0439.00" }] });
  assert.match((await submit(ENV, PERMIT, "10.0.0.1", f)).error, /permit request is already pending/);
  assert.equal((await submit(ENV, GOOD, "10.0.0.2", f)).status, "received");
});

test("unknown or malformed permit is rejected before any inbox call", async () => {
  reset();
  const { f, calls } = mock();
  assert.equal((await submit(ENV, { ...PERMIT, tik_num: "2026/9999.00" }, "10.0.0.3", f)).error, "unknown permit request");
  assert.equal((await submit(ENV, { ...PERMIT, pl_number: "101-1" }, "10.0.0.3", f)).error, "give pl_number or tik_num, not both");
  assert.ok(!calls.some((c) => /inbox/.test(c.url)));
});

test("schema: tik_num offered, neither id field required on its own", async () => {
  const { TOOL } = await import("./submit.mjs");
  assert.ok(TOOL.inputSchema.properties.tik_num);
  assert.ok(!TOOL.inputSchema.required.includes("pl_number"));
  assert.ok(!TOOL.inputSchema.required.includes("tik_num"));
});

// #530: the duplicate-pending check reads every page of open external-review issues.
function paged(pages, { failPage = 0 } = {}) {
  const calls = [];
  const f = async (url, init = {}) => {
    const u = String(url);
    calls.push({ url: u, method: init.method || "GET" });
    if (u.endsWith("data.json")) return new Response(JSON.stringify({ rows: [{ pl_number: "101-1" }] }));
    if ((init.method || "GET") !== "GET") return new Response("{}", { status: 201 });
    const page = Number(new URL(u).searchParams.get("page") || 1);
    if (page === failPage) return new Response("{}", { status: 502 });
    return new Response(JSON.stringify(pages[page - 1] || []));
  };
  return { f, calls };
}
const filler = (n, tag) => Array.from({ length: n }, (_, i) => ({ title: `[external-review] 101-${tag}${i}` }));

test("regression #530: a pending duplicate on page 2 is still rejected", async () => {
  reset();
  const { f, calls } = paged([filler(100, "9"), [{ title: "[external-review] 101-1" }]]);
  assert.match((await submit(ENV, GOOD, "11.0.0.1", f)).error, /already pending/);
  assert.ok(calls.some((c) => /[?&]page=2\b/.test(c.url)));
  assert.ok(!calls.some((c) => c.method === "POST"));
});

test("#530: a short first page ends the scan; a failed later page fails closed", async () => {
  reset();
  const one = paged([filler(3, "9")]);
  assert.equal((await submit(ENV, GOOD, "11.0.0.2", one.f)).status, "received");
  assert.ok(!one.calls.some((c) => /[?&]page=2\b/.test(c.url)));
  const broken = paged([filler(100, "9")], { failPage: 2 });
  assert.equal((await submit(ENV, GOOD, "11.0.0.3", broken.f)).error, "inbox unavailable");
  assert.ok(!broken.calls.some((c) => c.method === "POST"));
});

test("#530: hitting the page cap fails closed instead of opening an issue", async () => {
  reset();
  const { MAX_PENDING_PAGES } = await import("./submit.mjs");
  const { f, calls } = paged(Array.from({ length: MAX_PENDING_PAGES + 1 }, (_, p) => filler(100, `${p}x`)));
  assert.equal((await submit(ENV, GOOD, "11.0.0.4", f)).error, "inbox unavailable");
  assert.ok(!calls.some((c) => c.method === "POST"));
});
