// #846. Curated review leads from two forum meetings, not legal requirements.
// Keep the published privacy-redacted source, never participant identities.
const SOURCE = {
  id: "urban-forum-2026-10-14",
  title: "Ginot HaIr Urban Forum summary, meeting 14 October 2026",
  meeting_date: "2026-10-14",
  document_date: "2026-11-04",
  source_path: "docs/reviews/forum-2026-10-14/summary-redacted.pdf",
  source_kind: "community_forum_summary",
};
const D = "101-1389568", P = "101-1377753", A = "1993/0664.03";
function pattern(id, pages, cases, check, evidence_needed) {
  return { id, source: SOURCE, pages, cases, check, evidence_needed,
    status: "review_lead_not_verified_finding",
    legal_effect: "none established: verify applicable binding plan, policy status and exact clause; forum position is not law or an appeal decision",
    use_gate: "Check applicability to this case first. Mark unverified until the cited evidence has been read. Do not transfer numeric limits from another case or policy area.",
  };
}
export const OBJECTION_PATTERNS = [
  pattern("height-topography", [1, 3, 4, 5], [D,P,A],
    "Count visible floors on every frontage, entrance datum, roof access and setbacks; compare height and floor count separately with the applicable plan/policy. Sloping ground can make one frontage taller.",
    ["current sections and elevations with sheet/page", "governing policy map and table/clause", "controlling entrance and roof levels"]),
  pattern("facades-materials", [1], [D],
    "Check whether glass facades and uniform massing fit the street's materials, preservation character and natural topography. A forum preference alone does not prove a violation.",
    ["facade/material schedule", "street elevations", "applicable design/preservation provisions"]),
  pattern("mature-trees-excavation", [1,2,3,5], [D,P,A],
    "Reconcile mature trees, felling/retention colours and excavation/garage footprint. Test an underground setback or reduced excavation alternative rather than assuming replacement planting is enough.",
    ["numbered arborist survey and legend", "tree values and officer decision", "excavation/root-zone overlay and sections", "tested alternatives"]),
  pattern("usable-public-allocation", [1], [D],
    "Measure whether the brown-designated public allocation is usable, accessible and sufficient for its intended programme. Do not copy a minimum area from another plan.",
    ["land-use drawing and area table", "public programme and needs calculation", "access, dimensions and level plan"]),
  pattern("commercial-frontage", [1], [P],
    "Check the proposed ground-floor use against any applicable master-plan commercial-frontage policy and the forum's request for local trade; distinguish desired policy from a binding requirement.",
    ["policy map and legal status", "ground-floor use drawing", "current provisions on permitted uses"]),
  pattern("garage-access-alternatives", [1,2], [D,P],
    "Compare garage access with pedestrian connections and street safety. If garages are split, test consolidation or an underground connection without assuming it is feasible.",
    ["traffic and parking appendix", "access gradients, sightlines and pedestrian route", "alternative feasibility and utility constraints"]),
  pattern("fences-sidewalks", [2], [P],
    "Check fence height and continuous clear sidewalk width, including private gardens and street-edge encroachments. Treat the forum's width and fence figures as case-specific requests until their policy source is verified.",
    ["survey and street cross-sections", "public/private boundary", "accessible clear-width dimensions", "applicable fence and sidewalk policy"]),
  pattern("coverage-denominator", [2], [P],
    "Recalculate proposed footprint against the correct plot area and the applicable coverage rule. The forum asks whether coverage exceeds the limit; it does not establish that it does.",
    ["approved and proposed area tables", "plot denominator and footprint drawing", "applicable coverage clause"]),
  pattern("preservation-no-reconstruction-assumption", [2,3,5], [A],
    "Verify the preservation designation and restrictions on demolition, dismantling/reassembly, additions and building lines. A cited appeal at Rachel Imenu 17 is only a lead until its actual decision and applicability are checked.",
    ["9988 provisions and preservation map", "municipal conservation card and committee decision", "existing/proposed demolition drawing", "original appeal decision, case number and applicability"]),
  pattern("notice-versus-drawings", [5], [A],
    "Compare the notice's demolition, floors and units with every frontage/section and roof access. The forum alleges inaccurate publication and requests cancellation/republication; neither a procedural defect nor a remedy is verified from that allegation alone.",
    ["full dated signed notice and publication evidence", "current binding provisions, sections and roof plan", "official decision on publication sufficiency or remedy"]),
];
const NOV4_SOURCE = {
  id: "urban-forum-2026-11-04", title: "Ginot HaIr Urban Forum summary, 4 November 2026",
  meeting_date: "2026-11-04", document_date: "2026-11-04", source_path: "docs/reviews/forum-2026-11-04-source/summary-redacted.pdf",
  source_kind: "community_forum_summary",
};
// Extra observations support a review lead, never establish a legal breach.
const observedAgain = {
  "height-topography": [[1,2], [P,"2026/0439.00"]],
  "mature-trees-excavation": [[1,2], [P,"2026/0439.00"]],
  "commercial-frontage": [[1,2], [P,"2026/0439.00"]],
  "garage-access-alternatives": [[1], [P]],
  "fences-sidewalks": [[1,2], [P,"2026/0439.00"]],
  "coverage-denominator": [[1], [P]],
  "usable-public-allocation": [[1], [P]],
};
for (const p of OBJECTION_PATTERNS) {
  const observation = observedAgain[p.id];
  p.observations = [{ source: p.source, pages: p.pages, cases: p.cases }];
  if (observation) p.observations.push({ source: NOV4_SOURCE, pages: observation[0], cases: observation[1] });
}
function nov4Pattern(id, pages, cases, check, evidence) {
  const p = pattern(id, pages, cases, check, evidence);
  p.source = NOV4_SOURCE;
  p.observations = [{source: NOV4_SOURCE, pages, cases}];
  return p;
}
OBJECTION_PATTERNS.push(
  nov4Pattern("public-passage-continuity", [2], ["2026/0439.00"],
    "The forum reports a longstanding passage through the plot connecting Rachel Imenu to Palmach. Verify its physical history, legal status and alignment before requesting restoration; age alone does not prove an easement.",
    ["survey and proposed site plan", "approved rights/easements and municipal records", "documented passage alignment and accessible connection"]),
  nov4Pattern("construction-stage-sidewalk", [1,2], [P,"2026/0439.00"],
    "Check that excavation, shoring and site fencing preserve a continuous usable sidewalk during works as well as in the final plan. Forum width claims are not a measured survey or a universal statutory minimum.",
    ["surveyed current clear width", "excavation/shoring and temporary pedestrian plan", "final street section and verified applicable accessibility requirements"]),
  nov4Pattern("proportionate-no-objection-option", [2], ["101-1488261"],
    "The forum records a decision not to object to Inbal after considering the operational waste-handling improvement and existing paved access area. Consider no objection, clarification or conditions as outcomes, not only opposition. This is a forum outcome, not owner approval, a legal clearance, or a substitute for checking harm.",
    ["exact current application scope and previous approval", "existing surface, trees and actual footprint", "verified effects on neighbours, pedestrian access and operations"]),
);
export const PATTERN_RULES = {
  purpose: "Non-attributed review leads learned from two forum meetings; not a population frequency estimate, proven violation, standing instruction to object, or authority to file.",
  procedure: "Separate a planning objection, a permit objection and an appeal. The summary records proposed objections and mentions an older appeal; it supplies no verified appeal result for these cases.",
  deadlines: "Never calculate or replace an official deadline from a forum summary. Verify the latest official notice and publication record separately.",
  output: "For each relevant lead show source page, checked case evidence, applicable policy, measured difference, confidence, open questions and a proportionate request. Inapplicable or missing-evidence leads are not grounds for an asserted violation.",
};
