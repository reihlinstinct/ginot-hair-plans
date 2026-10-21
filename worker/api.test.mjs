import test from "node:test";
import assert from "node:assert/strict";
import { filterPlans, filterPermits, handleRequest } from "./api.mjs";

const rows = [
  { pl_number: "101-1", pl_name: "שימור אבן שפרוט", station_desc: "הפקדה להתנגדויות/השגות",
    objection_deadline_derived_60d_from_publication: "2026-12-09" },
  { pl_number: "101-2", pl_name: "בניין מגורים", station_desc: "אישור" },
  { pl_number: "101-3", pl_name: "תוספת קומה", station_desc: "בבדיקה תכנונית",
    objection_deadline_derived_60d_from_publication: "2026-11-01" },
];
const permits = [
  { mispar_bakasha: "2024-1", address: "עמק רפאים 12 מושבה גרמנית", status: "בטיפול", sugbakasha: "דירה" },
  { mispar_bakasha: "2024-2", address: "לינקולן 5", status: "אושר", sugbakasha: "תוספת" },
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
  assert.equal(filterPermits(permits, new URLSearchParams("street=רפאים"))[0].mispar_bakasha, "2024-1");
  assert.equal(filterPermits(permits, new URLSearchParams("status=אושר"))[0].mispar_bakasha, "2024-2");
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
