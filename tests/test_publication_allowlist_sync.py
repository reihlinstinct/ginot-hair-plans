"""#559: the three publication allowlists must stay in sync - the publish
step's git add list (what lands in the commit), the bundle verifier (what
the isolated publish job accepts) and the router's DATA_FILES (what may be
routed as a data PR). #761 review: data.json was in the first, missing
from the other two."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "ci"))

import permit_router


def _workflow_add_list():
    text = (ROOT / ".github/workflows/permit-feed.yml").read_text(encoding="utf-8")
    line = next(
        l
        for l in text.splitlines()
        if l.strip().startswith("git add") and "docs/index.json" in l
    )
    return {
        item
        for item in line.strip().split()[2:]
        if item.startswith("docs/") and "*" not in item
    }


def _bundle_allowlist():
    text = (ROOT / "scripts/ci/verify_publication_bundle.sh").read_text(
        encoding="utf-8"
    )
    allowed = re.search(r"allowed='\^\(data/\.\+\|(.+)\)\$'", text).group(1)
    return {
        alt.replace("\\.", ".")
        for alt in allowed.split("|")
        if alt.startswith("docs/") and "*" not in alt and "[" not in alt
    }


def test_publication_allowlists_stay_in_sync():
    workflow = _workflow_add_list()
    bundle = _bundle_allowlist()
    router = {p for p in permit_router.DATA_FILES if p.startswith("docs/")}
    assert workflow == bundle == router
    assert "docs/data.json" in workflow  # the #559 refresh must be publishable


def test_permit_workflow_regenerates_covered_site_after_reset_before_stage():
    text = (ROOT / ".github/workflows/permit-feed.yml").read_text()
    reset = text.index("git reset --hard origin/main")
    render = text.index(
        "python3 scripts/ci/check_docs_fresh.py --include-data-json --write", reset
    )
    stage = text.index("git add data/ docs/index.json", reset)
    assert reset < render < stage


def test_permit_feed_stages_language_fragments_from_the_i18n_source():
    # #972: a docs/*/permits*.html glob would stage a stray non-language
    # directory's files. The feed derives fragment paths from i18n instead.
    text = (ROOT / ".github/workflows/permit-feed.yml").read_text()
    assert "docs/*/permits" not in text
    assert "from ginot import i18n" in text and "FRAGMENTS=$(" in text
