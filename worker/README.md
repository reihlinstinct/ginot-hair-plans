# ginot-hair-api (Cloudflare Worker)

Read-only query layer over the site's static data files (owner request
2026-10-21). Stateless, no secrets, no storage, free plan. CORS open.

- `GET /` - endpoint index (JSON)
- `GET /plans?open=1&status=&q=&before=YYYY-MM-DD&limit=` - plans
- `GET /permits?street=&status=&type=&q=&limit=` - permit requests
- `GET /open` - the static open.json (open plans)
- `GET /status` - generated date + counts

Rate limiting is best-effort per isolate (120 req/min/IP, fixed window);
upstream data.json is edge-cached 5 minutes. Documented on the site's about
page.

## Deploy (owner, one time)

1. dash.cloudflare.com -> Workers & Pages -> ginot-hair-api.
2. `npx wrangler deploy` from this directory (or paste `api.mjs` in the
   dashboard editor).
3. Note the `*.workers.dev` URL and add it to the about-page API section.

## Test

`node --test worker/*.test.mjs` (no dependencies; runs in CI).

## Hosted MCP (ginot-hair-mcp)

Read-only remote MCP (Streamable HTTP, stateless) over the same public data: tools
`search_plans`, `get_plan`, `upcoming_objection_windows` (derived, not official),
`data_status`. No secrets, no writes. Source: `mcp.mjs`, config: `wrangler-mcp.toml`
(deploy: `npx wrangler deploy -c wrangler-mcp.toml`). Endpoint: `POST <workers.dev URL>/mcp`.

**Live endpoint:** `https://ginot-hair-mcp.reihlinstinct.workers.dev/mcp` (no auth, read-only, public data).

Verified with a generic HTTP client (2026-10-22): `initialize`, `tools/list` (4 tools),
`tools/call` (data_status, upcoming_objection_windows), notification -> 202, CORS preflight
-> 204 with `access-control-allow-origin: *`, GET -> 405 (POST-only, no SSE stream).
Replies are plain JSON (no sessions). NOT yet tested from the Claude, ChatGPT or Grok apps themselves.

Connect (per official docs; steps may change):
- Claude Code: `claude mcp add --transport http ginot-hair https://ginot-hair-mcp.reihlinstinct.workers.dev/mcp`
- Claude (web/Desktop): Settings > Connectors > Add custom connector, paste the URL
  ([docs](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp); free plan allows one custom connector).
- ChatGPT: enable developer mode, then add the URL as a custom MCP server
  ([docs](https://developers.openai.com/api/docs/guides/custom-mcp-server), [help](https://help.openai.com/en/articles/12584461)).
  OpenAI API: Responses API `mcp` tool with `server_url` set to the endpoint.
- Grok: API `mcp` tool with `server_url` ([docs](https://docs.x.ai/developers/tools/remote-mcp)); CLI: `grok mcp add` ([docs](https://docs.x.ai/build/features/mcp-servers)).

Test: `node --test worker/*.test.mjs`.

## External AI review submissions (ginot-hair-mcp-submit)

A separate write Worker with ONE MCP tool, `submit_review` (args: `pl_number`, `review`
40-1500 chars plain text, no links/HTML, `agent_name`, `key`). It never changes site data: it opens a
labelled issue in a private inbox repo for human review. Published reviews (after approval) are
labelled "external AI review, unverified"; they never replace or edit existing reviews.

- Submit key (public, NOT a secret, a speed bump only): `gh-submit-c2d1ea104108`. Real protection is the quarantine.
- Limits: 5 submissions per IP per hour, 50 per day, 8 KB body, one pending submission per plan.
- Rotate the key: edit `SUBMIT_KEY` in `worker/wrangler-submit.toml`, redeploy
  (`npx wrangler deploy -c wrangler-submit.toml`), update this README.
- Kill switch: set `DISABLED = "1"` in the same file and redeploy; the tool then refuses everything.
- Live endpoint: `POST https://ginot-hair-mcp-submit.reihlinstinct.workers.dev/` (MCP over HTTP, same connection steps as the read server, one tool: `submit_review`). End-to-end tested 2026-10-22 (wrong key refused, link text refused, valid submission quarantined as a private issue).
- Test: `node --test worker/*.test.mjs`.
