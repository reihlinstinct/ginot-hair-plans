import test from "node:test";
import assert from "node:assert/strict";
import { SECURITY_TXT } from "./securitytxt.mjs";
import { handleRequest as api } from "./api.mjs";
import { handleRequest as mcp } from "./mcp.mjs";
import { handleRequest as submit } from "./submit.mjs";

const U = "https://x.example/.well-known/security.txt";
const get = () => new Request(U);

test("security.txt has RFC 9116 required fields, Expires within a year, no personal email", () => {
  assert.match(SECURITY_TXT, /^Contact: https:\/\/github\.com\/reihlinstinct\/ginot-hair-plans\/security\/advisories\/new$/m);
  const exp = SECURITY_TXT.match(/^Expires: (.+)$/m)[1];
  assert.ok(!isNaN(Date.parse(exp)));
  assert.match(SECURITY_TXT, /^Preferred-Languages: he, en$/m);
  assert.ok(!/@/.test(SECURITY_TXT));
});

test("all three Workers serve security.txt on GET and HEAD (was 405/404)", async () => {
  for (const h of [(r) => api(r), (r) => mcp(r), (r) => submit(r, {})]) {
    const r = await h(get());
    assert.equal(r.status, 200);
    assert.match(r.headers.get("content-type"), /^text\/plain/);
    assert.equal(await r.text(), SECURITY_TXT);
    assert.equal((await h(new Request(U, { method: "HEAD" }))).status, 200);
  }
});

test("POST to the security.txt path is not served as the file", async () => {
  const r = await mcp(new Request(U, { method: "POST", body: "{}" }));
  assert.notEqual(await r.text(), SECURITY_TXT);
});
