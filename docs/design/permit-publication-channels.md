# Publication channels for section 149 permit notices (Jerusalem)

Where a section 149 notice (Planning and Building Law 1965) for a permit
request - such as 2026/0439.00, Hapalmach 41 - is published, offline and
online. Researched 2026-10-25; every channel below names its source.

## Statutory channels (s.149)

1. **Direct notice to owners, holders and neighbors.** The committee must
   notify the property owners/holders and adjoining owners, and anyone the
   committee believes may be harmed. Delivered by mail; in Jerusalem this is
   handled by a municipality-designated publishing company at the
   applicant's expense.
   Sources: Planning Administration procedure 2025/7 on s.149 notice
   delivery (gov.il, published 2025-07-15)
   <http://www.gov.il/he/pages/rz_section_149>;
   Jerusalem municipality, building-permit process page
   <https://www.jerusalem.muni.il/he/residents/planningandbuilding/licensingconstruction/buildingpermit/>
2. **A sign posted on the property.** This is what the owner photographed
   on 2026-10-25 for 2026/0439.00 - see
   `docs/reviews/s149_notice_2026-0439.00.md`.
3. **Newspaper advertisement.** The municipal instruction pages
   retrieved for this research (Herzliya, Omer, Ashkelon - not Jerusalem)
   each require ads in two Hebrew daily newspapers, at least one widely
   circulated; the applicant arranges and pays. Jerusalem's current
   newspaper requirement is UNVERIFIED (see Open ends).
   Sources: Herzliya engineering portal
   <https://handasa.herzliya.muni.il/construclicens/noticeofrelief/>;
   Omer publication procedure
   <https://omer.complot.co.il/tichniun/pirsum/>;
   Ashkelon s.149 instructions PDF
   <https://ashkelon-temp.complot.co.il/wp-content/uploads/2023/08/052022_הנחיות-לפרסום-לפי-סעיף-149.pdf>
   Newspaper ads are a PRINT channel - they are not systematically
   available online. Jerusalem reportedly eased its permit-publication
   requirements/costs (JDN, Hebrew)
   <https://archive.jdn.co.il/breakingnews/142774/>;
   the current Jerusalem-specific newspaper list was not retrieved.

## Online channels

1. **Official: the municipality's public permit viewer (ykpubdata).**
   <https://ykpubdata.jerusalem.muni.il/> - the public licensing-data
   viewer whose backend API (jerbasicserviceapi.jerusalem.muni.il,
   Rishui system 26400046) this repo's permit feed reads
   (`scripts/vpn/permit_feed.py`). The viewer exposes each request's
   process steps, including the actual s.149 publication milestones
   ("תחילת פרסום בפועל" / "השלמת פרסום"). Request 2026/0439.00 is listed
   there: our feed row shows status "תחילת פרסום בפועל"-derived
   publication_start 2026-10-18 (row checked 2026-10-24). Caveat: the
   feed pipeline fills publication_start from the municipality's
   "תחילת פרסום בפועל" process step, but whether the municipality
   recorded an actual or a planned start in that step cannot be
   distinguished from the data alone (no separate execution-date field
   is exposed); the one-day gap to the handwritten posting date
   (19.10) is consistent with either reading.
   The notice itself directs the public online: the scanned request is on
   the municipality website under "תכנון ובנייה > תיק רישוי בניה", and
   objections are filed via the online form
   "תכנון ובנייה > כתב התנגדות לבקשה להיתר". The licensing portal page
   <https://www.jerusalem.muni.il/he/residents/planningandbuilding/licensingconstruction/>
   links "סטטוס תיק רישוי ובנייה" and "בירור מצב בקשות תכנון ובנייה".
2. **Third-party archive: over.org.il ("גרסאות לעם").**
   <https://www.over.org.il/sources/ykpubdata> - a civic project that
   continuously downloads and versions the ykpubdata dataset with
   source links. Searchable online; presence of this specific tik could
   not be verified statically (JS application).

## Explicitly NOT channels for permit s.149 notices

- **Mavat / iplan** (mavat.iplan.gov.il, iplan.iplan.gov.il): national
  PLAN tracks (101-xxxxxxx) - deposits and approvals, not permit
  requests. Plan deposit notices also appear via the committees' gazette
  appendices (e.g. apps.land.gov.il IturTabotData "פרסום הפקדה" PDFs).
- **Yalkut / the Israel Gazette**: plan approvals and similar statutory
  publications; s.149 permit-request notices are not gazette items.

## Summary for 2026/0439.00

- Online: listed in the official ykpubdata viewer (verified via our
  feed); expected in the over.org.il archive (unverified per-tik).
- Offline: site sign photographed 2026-10-25 (posted 19.10.26).
  Neighbor notices by mail are a statutory requirement, but their actual
  delivery for this request is UNVERIFIED. Newspaper ad(s) expected but
  not verified.
- Objections until 13.11.2026 via the municipality's online objection
  form (see the evidence note for the verified notice text).

## Open ends

- The current Jerusalem-specific newspaper requirement (which papers,
  how many) was not retrieved from an official Jerusalem page; the
  municipality's "למידע על הפרסום" link is JS-rendered and did not
  resolve to a readable page in this research round.
- Direct deep-link format into a specific ykpubdata tik is unknown
  (JS application over a procedure-call API).
