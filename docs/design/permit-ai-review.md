# On-demand and automatic AI review of permit applications (#520)

Design-first. No code yet; implementation lands as reviewed PRs. Free
resources only, public data only, no personal attribution, and every
municipal fetch goes through the approved tunnel policy (3 s serial,
stop-red on anti-bot challenge). The Palmach 41 review
(`docs/reviews/palmach41/`) is the quality bar and the output precedent.

## Inputs (all already collected)

- `data/permit_requests.json` - the application registry the site's
  "בקשות היתר (DRAFT)" section renders 1:1 (statuses, parcels, addresses,
  publication fields).
- Active-publications API (PD900) - official objection deadline and
  publication start, per the existing publications pipeline.
- Municipality viewer feed via the existing l2tp tunnel for permit-file
  details - already rate-limited and checkpointed; no new fetch path.

## Triggers

1. **Weekly refresh flag**: the existing weekly run marks rows whose
   publication-relevant status transitioned (ממתין לאישור נוסח פרסום →
   תחילת פרסום → active objection window). Only those rows queue for
   review generation - a diff against the previous feed, not a full scan.
2. **Manual**: workflow_dispatch by tik number for one-off requests.

## Generation route (free only)

- Primary: GitHub Models free tier using the Actions `GITHUB_TOKEN`. The
  free-tier quota is an open verification step - measure it in the
  implementing PR before wiring the weekly trigger, and record the measured
  quota in that PR. If the quota cannot cover the weekly queue, only the
  manual trigger ships.
- Fallback: an agent-run step producing the same artifact through the same
  template and gates.
- Never: paid tiers, external API keys, or sending permit data to any
  endpoint outside the approved route.

## Output

- `docs/reviews/<tik>/` per application: HTML page plus PDF, published via
  the existing Pages build, following the palmach41 directory precedent
  (README, review html/md, source links).
- Every review carries the standing disclaimers (AI draft for public
  review, not professional or legal advice, not a filed objection) and a
  sources section linking each fact to its public record.

## Quality gates (before any publication)

1. Schema regression test: generated artifact validates against a checked-in
   schema (required sections, disclaimer present, source links resolve to
   repo-known hosts).
2. Spot-check: a human (or the owner-delegated reviewer) spot-checks each
   new review before its directory is published, exactly as the Palmach 41
   review was handled. Automatic generation never equals automatic
   publication.
3. The review makes no legal determinations: it lists facts, policy
   comparisons and open questions, in the established review style.

## Non-goals

No objection filing (see #570), no private data, no attribution of opinions
to individuals, no relaxation of tunnel politeness, no paid services.

## Open questions

1. Measured GitHub Models free quota vs the weekly queue size.
2. Minimum status set that justifies a review (only active objection
   windows, or also pre-publication?).
3. PDF generation: reuse the palmach41 print stylesheet route or a build
   step.
