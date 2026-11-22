"""Regression (#405): the permit-feed publish step must invoke the permits
fragment renderer and commit the fragment, under set -e - no non-fatal
fallback that could ship a data update with a stale site."""

from pathlib import Path


def test_publish_step_renders_and_commits_permits_fragment():
    workflow = (
        Path(__file__).parent.parent / ".github/workflows/permit-feed.yml"
    ).read_text()
    publish = workflow.split("Prepare publication commit", 1)[1].split("- name:", 1)[0]
    assert "python3 scripts/render_permits_page.py" in publish
    render_line = next(
        line
        for line in publish.splitlines()
        if "render_permits_page.py" in line and "python3" in line
    )
    assert "||" not in render_line  # no non-fatal fallback: set -e governs
    add_line = next(
        line
        for line in publish.splitlines()
        if line.strip().startswith("git add") and "docs/index.json" in line
    )
    assert "docs/permits.html" in add_line

    assert "docs/permit-points.json" in add_line
    # #559: the batch refreshes permits[] inside data.json - it must be
    # staged into the publication commit like the other generated files.
    assert "docs/data.json" in add_line


def test_publish_step_commits_default_permits_subset():
    """#441: the page loads docs/permits-default.html first, so a feed batch
    must commit it with the full fragment or new default rows go stale."""
    workflow = (
        Path(__file__).parent.parent / ".github/workflows/permit-feed.yml"
    ).read_text()
    publish = workflow.split("Prepare publication commit", 1)[1].split("- name:", 1)[0]
    add_line = next(
        line
        for line in publish.splitlines()
        if line.strip().startswith("git add") and "docs/index.json" in line
    )
    assert "docs/permits-default.html" in add_line.split()


def test_publish_step_stages_locale_index_pages():
    """#1000: locale index.html pages are data-derived (the #996 search
    datalist of plan numbers is server-rendered into every locale), so the
    FRAGMENTS list must stage docs/<lang>/index.html for every non-default
    language. Run 43733250766 failed the #874 cleanliness guard on exactly
    those five files left unstaged. #979: the path rule lives in one
    place - scripts/ci/permit_fragments.py - shared by the workflow (this
    staging) and permit_router (publication allowlist), and this test
    EXECUTES it and compares the exact path set against i18n."""
    import subprocess
    import sys

    root = Path(__file__).parent.parent
    workflow = (root / ".github/workflows/permit-feed.yml").read_text()
    publish = workflow.split("Prepare publication commit", 1)[1].split("- name:", 1)[0]
    # The workflow calls the shared script; no inline copy of the rule.
    assert "FRAGMENTS=$(python3 scripts/ci/permit_fragments.py)" in publish
    assert "FRAGMENTS=$(python3 -c" not in publish
    # The router resolves the same paths through the same module (#979).
    router = (root / "scripts/ci/permit_router.py").read_text()
    assert "permit_fragments" in router
    # The computed list must actually be staged (#1001 review): pinning the
    # rule is moot if $FRAGMENTS falls off the git add line.
    add_line = next(
        line
        for line in publish.splitlines()
        if line.strip().startswith("git add") and "docs/index.json" in line
    )
    assert "$FRAGMENTS" in add_line.split()

    out = subprocess.run(
        [sys.executable, "scripts/ci/permit_fragments.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    sys.path.insert(0, str(root / "src"))
    from ginot import i18n

    langs = [c for c in i18n.lang_codes() if c != i18n.default_lang()]
    assert langs, "expected at least one non-default language"
    expected = {
        f"docs/{lang}/{page}"
        for lang in langs
        for page in ("index.html", "permits.html", "permits-default.html")
    }
    assert set(out) == expected
    # No default-language duplicate: docs/index.html is staged explicitly.
    assert all(not p.startswith(f"docs/{i18n.default_lang()}/") for p in out)
