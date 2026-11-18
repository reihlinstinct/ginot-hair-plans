# Permit-aware MCP reads and approval-gated objection preparation (#570)

Design only. **No filing, no submission route and no new authority is created
here.** Current authority remains: no autonomous Ginot filing. Any eventual
submission step needs per-case, per-document, per-destination owner approval;
no public secret or tool flag counts as consent. Route and legal requirements
must be verified before any submit implementation.

## Current server (measured at 6cc7911)

`src/ginot/mcp_server.py` exposes four read-only tools over the public plan
data - `search_plans`, `get_plan`, `upcoming_objection_windows`,
`data_status` - over stdio, public fields only (`public(row)`). Nothing
permit-specific exists.

## Proposed additions

### 1. Permit reads (public, same privacy class as today)

- `search_permits` - filter the public permit feed (`data/permit_requests.json`)
  by street, neighborhood, status, publication window. Same field rules as
  the site: raw provenance preserved, no invented values.
- `get_permit` - one tik by id, including parcels_observed, publication
  dates and address fields exactly as stored.
- `get_permit_reviews` - the published review artifacts for a tik when they
  exist under `docs/reviews/`.
- All three reuse the existing feed files; no new municipal fetching is
  added to the MCP path. The server stays a reader of pre-built public data.

### 2. Objection preparation (private, local, never submitted by the server)

- `prepare_objection_draft` - assembles a structured Hebrew draft (case
  facts, cited master-plan clauses with page references, open questions)
  from public data plus caller-supplied arguments. Output is a local
  document the owner reviews; the tool performs no network call, no email,
  no upload.
- The draft always carries the review's standing disclaimers (not legal
  advice, not filed) and lists which facts came from which public source so
  the owner can verify each line.
- Privacy boundaries follow the traffic-complaint-form repo's `docs/MCP.md`
  as the reference pattern for separating public reads from private
  preparation (that document lives in the sibling repo and is consulted at
  implementation time; its delivery semantics are NOT reused - this server
  delivers nothing).

### 3. Explicitly deferred: submission

The issue's user request mentions filing objections. A submission route, if
ever built, is a separate issue requiring: verified municipal submission
channel and its legal requirements, authenticated case-owner identity, and
exact per-case approval of document and destination. It is out of scope for
every PR this design spawns.

## Implementation shape

- One PR for the three read tools (schema-stable feed reads + tests with
  synthetic feed fixtures), one PR for the draft tool (template +
  provenance list + tests). No cross-cutting refactor.
- `call_tool` is already over the C901 ratchet and grandfathered; new tools
  are added as small handler functions so the ratchet entry only shrinks.
- Tool count and names are added to the existing MCP tests; stderr/stdout
  protocol behavior unchanged.

## Open questions

1. Draft language/format: Hebrew DOCX-style markdown, or plain text matching
   the municipal objection form's fields (needs the form's current fields -
   verification step)?
2. Should `prepare_objection_draft` accept a deadline argument and compute
   the objection window from `upcoming_objection_windows` logic, or stay
   purely textual?
