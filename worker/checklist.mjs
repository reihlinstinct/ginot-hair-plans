// Review checklist for outside AIs. Static public text, no fetches.
// Only items with a named source are stated as requirements. Everything else is a
// review question for the reader, not a claim about what the law requires.
export const SRC_GOV = "https://www.gov.il/he/service/filing-objection";
const DOCS = "from_documents";
const EXT = "needs_source_outside_connector";
const JUDG = "judgment";
const NONE = "none established: review question, do not present as a legal requirement";

export const CHECKLIST = {
  version: 1,
  purpose: "What to check before calling a plan review finished. The connector holds metadata (name, status, dates, area, a map point) plus published reviews, not the plan documents.",
  tagging_rule: "Tag every factual claim [verified: <where>] or [unverified: <what is missing>]. Use [read from: <field or tool>] for connector data. Put opinions on lines starting with 'judgment:'. Never fill a gap with a guess or a general-knowledge figure.",
  derived_deadline_rule: "objection_deadline_derived_60d_from_publication is computed, not official. Say so next to every deadline. The official date is in the signed deposit notice on the plan's Mavat page. depositing_date is the committee's deposit decision date and is not the publication date.",
  items: [
    { id: "docs-complete", area: "document completeness", check: "Which deposit documents exist (provisions, binding drawing, appendices) and which are missing or unreadable (scans, bad OCR)?", verifiable: DOCS, requirement_source: NONE },
    { id: "notice-publication", area: "objection window and notices", check: "Publication date in the press and the signed notice text. Is the stated final date the notice's own, or derived?", verifiable: EXT, requirement_source: "60 days from publication: " + SRC_GOV },
    { id: "notice-how-to-object", area: "objection window and notices", check: "How and where to file, and any form requirements the notice itself states.", verifiable: EXT, requirement_source: "the plan's own deposit notice (quote it); online service: " + SRC_GOV },
    { id: "authority", area: "procedure", check: "Which committee deposits the plan (local or district) and under which provision the provisions text says it is promoted.", verifiable: DOCS, requirement_source: NONE },
    { id: "plan-relation", area: "governing plan", check: "Which approved plans it changes, replaces or leaves in force, and whether the provisions say which parts of the earlier plan still apply.", verifiable: DOCS, requirement_source: NONE },
    { id: "area-consistency", area: "area and rights consistency", check: "Do plan area, plot area, approved vs proposed area tables and any building-area claims agree across documents? Name every unexplained difference with both numbers and pages.", verifiable: DOCS, requirement_source: NONE },
    { id: "units-consistency", area: "area and rights consistency", check: "Unit counts: existing, proposed, added. Do all documents agree?", verifiable: DOCS, requirement_source: NONE },
    { id: "rights-table", area: "rights", check: "Building rights, coverage, floors and height from the rights table. If the table is unreadable, say it was not read.", verifiable: DOCS, requirement_source: NONE },
    { id: "setbacks-heights", area: "setbacks, heights, parking", check: "Compare proposed setbacks, heights and parking with the governing plan's values. Report the delta, not an adjective.", verifiable: DOCS, requirement_source: NONE },
    { id: "preservation", area: "preservation and conditions", check: "Is the building or area marked for preservation? What do the provisions require (facades, materials, fences, trees)?", verifiable: DOCS, requirement_source: NONE },
    { id: "conditions", area: "preservation and conditions", check: "Permit conditions: demolitions of violations, trees, runoff, phasing, time to implement.", verifiable: DOCS, requirement_source: NONE },
    { id: "stated-vs-unexplained", area: "changes", check: "Split what the plan states it changes from changes visible in the numbers that the text does not explain.", verifiable: DOCS, requirement_source: NONE },
    { id: "use-rules", area: "changes", check: "For any new use (for example a rooftop terrace): are hours, noise, privacy or access rules stated? If not, say they are missing.", verifiable: DOCS, requirement_source: NONE },
    { id: "street-fabric", area: "context", check: "Street frontage, commercial frontage, balconies, traffic and parking impact as stated in the documents.", verifiable: DOCS, requirement_source: NONE },
    { id: "neighbours", area: "context", check: "Neighbouring plans in the same or nearby sites and their stage (search_plans).", verifiable: "from_connector", requirement_source: NONE },
    { id: "who-can-object", area: "standing", check: "Who the reader is and whether they may object. The connector cannot answer this.", verifiable: EXT, requirement_source: "gov.il service page says anyone who feels harmed may object within the period: " + SRC_GOV },
    { id: "open-questions", area: "output", check: "End with open questions and a short list of what you still cannot see even with all tools.", verifiable: JUDG, requirement_source: NONE },
  ],
  caveat: "Public data only. Not legal advice and not an official document. Only the objection period is sourced here; confirm any other requirement in the official notice or the law text before stating it.",
};

export const PROMPT = {
  name: "review_plan",
  description: "Review one plan with the checklist and strict verified/unverified tagging.",
  arguments: [{ name: "pl_number", description: "e.g. 101-1377753", required: true }],
};

export function promptText(pl) {
  return `Review plan ${pl}. Call get_plan, then get_review_checklist, then get_review if a published review exists. ` +
    "Go through every checklist item. Tag each factual claim [verified: where] or [unverified: what is missing] and [read from: field/tool] for connector data. " +
    "Keep judgment on lines starting 'judgment:'. Do not invent figures. Say which derived dates are not official. " +
    "End with open questions and what you still cannot see.";
}
