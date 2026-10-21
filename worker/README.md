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
