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
    computed FRAGMENTS list must stage docs/<lang>/index.html for every
    non-default language. Run 43733250766 failed the #874 cleanliness
    guard on exactly those five files left unstaged. The templates are
    extracted from the workflow and checked against i18n.lang_codes()
    independently - no exec of workflow text."""
    import re
    import sys

    workflow = (
        Path(__file__).parent.parent / ".github/workflows/permit-feed.yml"
    ).read_text()
    publish = workflow.split("Prepare publication commit", 1)[1].split("- name:", 1)[0]
    m = re.search(r'FRAGMENTS=\$\(python3 -c "(.*?)"\)', publish, re.DOTALL)
    assert m, "FRAGMENTS assignment not found in the publish step"
    expression = m.group(1)
    # The one-liner must iterate every non-default language itself.
    assert "i18n.lang_codes()" in expression
    assert "i18n.default_lang()" in expression
    templates = re.findall(r"f'(docs/\{c\}/[^']+)'", expression)
    assert templates, "no docs/<lang>/ f-string templates in FRAGMENTS"
    # The computed list must actually be staged (#1001 review): pinning the
    # expression is moot if $FRAGMENTS falls off the git add line.
    add_line = next(
        line
        for line in publish.splitlines()
        if line.strip().startswith("git add") and "docs/index.json" in line
    )
    assert "$FRAGMENTS" in add_line.split()

    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from ginot import i18n

    langs = [c for c in i18n.lang_codes() if c != i18n.default_lang()]
    assert langs, "expected at least one non-default language"
    staged = set()
    for template in templates:
        # A template may pack several space-separated paths in one f-string.
        for lang in langs:
            staged.update(template.format(c=lang).split())
    for lang in langs:
        for page in ("index.html", "permits.html", "permits-default.html"):
            assert f"docs/{lang}/{page}" in staged, (
                f"FRAGMENTS drops docs/{lang}/{page}"
            )
    # No default-language duplicate: docs/index.html is staged explicitly.
    assert all(not p.startswith(f"docs/{i18n.default_lang()}/") for p in staged)
