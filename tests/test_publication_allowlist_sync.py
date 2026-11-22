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
sys.path.insert(0, str(ROOT / "src"))

import permit_router

from ginot import i18n

FRAGMENT_NAMES = ("index.html", "permits.html", "permits-default.html")


def _language_codes():
    return frozenset(i18n.lang_codes()) - {i18n.default_lang()}


def _expected_language_fragments():
    # The feed stages these via $FRAGMENTS (#999); the router accepts them
    # through _language_permit_fragment (#942).
    return {
        f"docs/{code}/{name}" for code in _language_codes() for name in FRAGMENT_NAMES
    }


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
    """(static paths, language fragments) the bundle verifier accepts."""
    text = (ROOT / "scripts/ci/verify_publication_bundle.sh").read_text(
        encoding="utf-8"
    )
    allowed = re.search(r"allowed='\^\(data/\.\+\|(.+)\)\$'", text).group(1)
    static, fragments = set(), set()
    for alt in allowed.split("|"):
        if "*" in alt or "[" in alt:
            continue
        path = alt.replace("\\.", ".")
        parts = path.split("/")
        if (
            len(parts) == 3
            and parts[0] == "docs"
            and parts[1] in _language_codes()
            and parts[2] in FRAGMENT_NAMES
        ):
            fragments.add(path)
        elif path.startswith("docs/"):
            static.add(path)
    return static, fragments


def test_publication_allowlists_stay_in_sync():
    workflow = _workflow_add_list()
    bundle_static, _ = _bundle_allowlist()
    router = {p for p in permit_router.DATA_FILES if p.startswith("docs/")}
    assert workflow == bundle_static == router
    assert "docs/data.json" in workflow  # the #559 refresh must be publishable


def test_language_fragments_stay_in_sync_with_i18n():
    # #999 follow-up: run 43846768869's bundle was rejected because the
    # verifier and the router lacked the locale index.html the workflow had
    # started staging. Both must cover every non-default i18n language.
    expected = _expected_language_fragments()
    _, bundle_fragments = _bundle_allowlist()
    assert bundle_fragments == expected
    assert all(permit_router._data_path(p) for p in expected)


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
    assert "scripts/ci/permit_fragments.py" in text and "FRAGMENTS=$(" in text
