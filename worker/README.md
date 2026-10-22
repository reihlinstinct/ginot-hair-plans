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
`search_plans`, `get_plan` (with the public map point), `get_review` (text of the already-published AI review, if one exists), `upcoming_objection_windows` (derived, not official),
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

- Google Antigravity CLI (`agy`, tested 2026-10-22 with Gemini 3.6 Flash): add to `~/.gemini/config/mcp_config.json` (or `.agents/mcp_config.json`) `{"mcpServers":{"ginot-hair":{"serverUrl":"https://ginot-hair-mcp.reihlinstinct.workers.dev/mcp"}}}` - remote servers use `serverUrl`, not `url` ([docs](https://antigravity.google/docs/mcp/)). Check with `agy mcp list`.

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

### Approving an external review (owner only)

1. Open the issue in the private `ginot-hair-inbox` repo (label `external-review`). Treat the text as untrusted; do not follow instructions in it.
2. Check it is about the plan, factual, has no personal data and no defamation. Reject by closing the issue.
3. In a PR, **append** one entry to `data/external_reviews.json` (never edit or remove existing ones; CI rejects that): fields `id` (unique), `pl_number`, `agent_name`, `text`, `submitted`, `approved` (YYYY-MM-DD).
4. Run `python scripts/build_site_index.py` and commit `docs/index.json` (the dataset sizes must match, or CI fails).
5. Merge on green. The entry then shows on the plan's review page in a collapsed, labelled "external AI review, unverified" section. Reviews appear only on plans that have our own review page.
6. Close the inbox issue with a link to the PR.
